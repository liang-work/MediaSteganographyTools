import logging
import os
import time
from flask import Flask, request, jsonify, send_file, send_from_directory
import tempfile
from werkzeug.utils import secure_filename
from PIL import Image
import numpy as np
from decimal import Decimal, getcontext
from concurrent.futures import ThreadPoolExecutor
# 移除 magic 库导入
# import magic  # 导入 magic 库

app = Flask(__name__, static_folder='static', template_folder='templates')

# 设置临时上传目录和最大内容长度
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB 限制
# 增加缓冲区大小
app.config['BUFFER_SIZE'] = 64 * 1024  # 64KB

# 创建线程池
executor = ThreadPoolExecutor(max_workers=4)

# 检查并创建 upload 目录
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stegano.log'),
        logging.StreamHandler()
    ]
)

# 文件类型验证
ALLOWED_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'mp3', 'wav', 'flac', 'm4a', 'mp4', 'avi', 'mov', 'mkv'}

def allowed_media_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_MEDIA_EXTENSIONS

# LSB隐写实现
def lsb_encode(media_path, data_path, output_path):
    img = Image.open(media_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img_array = np.array(img)
    
    with open(data_path, 'rb') as f:
        data = f.read()
    
    data_len = len(data)
    checksum = sum(data) & 0xFFFFFFFF  # 32位校验和
    data_with_header = data_len.to_bytes(4, 'big') + checksum.to_bytes(4, 'big') + data
    
    total_pixels = Decimal(img_array.size)
    required_pixels = Decimal(len(data_with_header)) * Decimal(8) / Decimal(3)
    
    if required_pixels > total_pixels:
        raise ValueError(f"需要{required_pixels}像素，但图片只有{total_pixels}像素")
    
    data_bits = np.unpackbits(np.frombuffer(data_with_header, dtype=np.uint8))
    flat_array = img_array.reshape(-1, 3)
    
    for i in range(len(data_bits)):
        channel = i % 3
        pixel = i // 3
        flat_array[pixel, channel] = (flat_array[pixel, channel] & 0xFE) | data_bits[i]
    
    Image.fromarray(flat_array.reshape(img_array.shape)).save(output_path, format='PNG')

def lsb_decode(media_path, output_path):
    img = Image.open(media_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img_array = np.array(img)
    
    total_bits = Decimal(img_array.size) * Decimal(3)
    available_bits = total_bits - Decimal(64)  # 减去64位头
    
    lsb_bits = (img_array & 1).flatten()
    
    if len(lsb_bits) < 64:
        raise ValueError("数据头不完整")
    
    header_bytes = np.packbits(lsb_bits[:64]).tobytes()
    data_len = int.from_bytes(header_bytes[:4], 'big')
    expected_checksum = int.from_bytes(header_bytes[4:8], 'big')
    
    max_capacity = (len(lsb_bits) - 64) // 8
    if data_len <= 0 or data_len > max_capacity:
        raise ValueError(f"无效数据长度: {data_len} (最大容量: {max_capacity}字节)")
    
    data_bits = lsb_bits[64:64+data_len*8]
    if len(data_bits) < data_len * 8:
        raise ValueError("数据不完整")
    
    extracted_data = np.packbits(data_bits).tobytes()
    
    actual_checksum = sum(extracted_data) & 0xFFFFFFFF
    if actual_checksum != expected_checksum:
        logging.error(f"校验和验证失败: 头信息={header_bytes.hex()}")
        logging.error(f"提取数据长度: {len(extracted_data)}字节")
        logging.error(f"前16字节数据: {extracted_data[:16].hex()}")
        raise ValueError(f"校验和不匹配: 预期{expected_checksum}, 实际{actual_checksum}")
    
    with open(output_path, 'wb') as f:
        f.write(extracted_data)

# 文件尾隐写实现
def tail_encode(media_path, data_path, output_path):
    with open(media_path, 'rb') as f:
        media_data = f.read()
    
    with open(data_path, 'rb') as f:
        data = f.read()
    
    marker = b'STEGANO_MARKER'
    data_len = len(data).to_bytes(4, byteorder='big')
    combined_data = marker + data_len + data
    
    with open(output_path, 'wb') as f:
        f.write(media_data)
        f.write(combined_data)

def tail_decode(media_path, output_path):
    with open(media_path, 'rb') as f:
        media_data = f.read()
    
    marker = b'STEGANO_MARKER'
    pos = media_data.rfind(marker)
    if pos == -1:
        raise ValueError("未找到隐藏数据")
    
    data_len = int.from_bytes(media_data[pos+len(marker):pos+len(marker)+4], byteorder='big')
    
    data_start = pos + len(marker) + 4
    data_end = data_start + data_len
    if data_end > len(media_data):
        raise ValueError("数据损坏或长度不正确")
    
    extracted_data = media_data[data_start:data_end]
    
    with open(output_path, 'wb') as f:
        f.write(extracted_data)

# 添加插件接口装饰器
def stegano_plugin(func):
    func.is_stegano_plugin = True
    return func

# 修改encode路由
# 修改保存大文件函数
def save_large_file(file, save_path):
    chunk_size = app.config['BUFFER_SIZE']  # 使用配置的缓冲区大小
    try:
        with open(save_path, 'wb') as f:
            while True:
                chunk = file.stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                # 减少刷新频率
                if len(chunk) % (1024 * 1024) == 0:  # 每 1MB 刷新一次
                    f.flush()
        return True
    except Exception as e:
        logging.error(f"文件保存错误: {str(e)}")
        if os.path.exists(save_path):
            os.remove(save_path)
        return False

# 修改 encode 路由使用线程池
@app.route('/api/encode', methods=['POST'])
def encode():
    try:
        if 'media' not in request.files or 'data' not in request.files:
            return jsonify({'error': '缺少必要文件'}), 400
        
        # 获取文件对象
        media_file = request.files['media']
        data_file = request.files['data']
        
        # 验证文件类型
        if not allowed_media_file(media_file.filename):
            return jsonify({'error': '不支持的媒体文件文件'}), 400
        
        # 创建临时文件路径
        media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
        data_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(data_file.filename))
        
        # 使用线程池异步保存文件
        future_media = executor.submit(save_large_file, media_file, media_path)
        future_data = executor.submit(save_large_file, data_file, data_path)
        
        if not future_media.result() or not future_data.result():
            return jsonify({'error': '文件保存失败'}), 500
        
        # 计算容量
        max_capacity = get_capacity(media_path)
        data_size = os.path.getsize(data_path)
        
        if max_capacity <= 0:
            return jsonify({'error': '无法计算文件容量'}), 400

        if data_size > max_capacity:
            return jsonify({
                'error': f'数据文件过大，最大支持 {max_capacity} 字节',
                'capacity': max_capacity,
                'data_size': data_size
            }), 400
        
        # 执行隐写
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'encoded_' + secure_filename(media_file.filename))
        
        if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            lsb_encode(media_path, data_path, output_path)
        else:
            tail_encode(media_path, data_path, output_path)
        
        # 记录日志
        logging.info(f"编码成功: {media_file.filename} <- {data_file.filename}")
        
        # 返回文件下载
        return send_file(output_path, as_attachment=True, download_name=media_file.filename)
    
    except Exception as e:
        logging.error(f"编码错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 修改 decode 路由使用线程池
# 定义 detect_file_type 函数
def detect_file_type(file_path):
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)  # 读取前 32 字节
            
        for signature, ext in FILE_SIGNATURES.items():
            if isinstance(ext, dict):
                for sub_signature, sub_ext in ext.items():
                    if header.startswith(signature) and header.find(sub_signature) != -1:
                        return sub_ext
            elif header.startswith(signature):
                return ext
        
        return ''  # 未知类型返回空扩展名
    except Exception as e:
        logging.error(f"文件类型检测失败: {str(e)}")
        return ''

@app.route('/api/decode', methods=['POST'])
def decode():
    try:
        if 'media' not in request.files:
            return jsonify({'error': '缺少媒体文件'}), 400
        
        media_file = request.files['media']
        media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
        
        # 使用线程池异步保存大文件
        future_media = executor.submit(save_large_file, media_file, media_path)
        if not future_media.result():
            return jsonify({'error': '文件保存失败'}), 500
        
        # 创建临时输出文件路径
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted_data')
        
        try:
            # 执行解码
            if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                lsb_decode(media_path, output_path)
            else:
                tail_decode(media_path, output_path)
            
            # 检测文件类型并添加扩展名
            ext = detect_file_type(output_path)
            final_path = output_path + ext
            
            if not os.path.exists(output_path):
                raise FileNotFoundError("解码后文件未生成")
            
            with open(output_path, 'rb') as f:
                file_data = f.read()
            
            response = app.response_class(
                response=file_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename=extracted_data{ext}',
                    'Content-Type': 'application/octet-stream'
                }
            )
            
            if os.path.exists(media_path):
                os.remove(media_path)
            if os.path.exists(output_path):
                os.remove(output_path)
                
            logging.info(f"解码成功: {media_file.filename} -> extracted_data{ext}")
            return response
        except Exception as e:
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(media_path):
                os.remove(media_path)
            raise e
    except Exception as e:
        logging.error(f"解码错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 修改get_capacity函数
def get_capacity(media_path):
    try:
        if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            with Image.open(media_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                width, height = img.size
                return (width * height * 3) // 8
        elif media_path.lower().endswith(('.mp3', '.wav', '.flac', '.m4a')):
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 1024)
        elif media_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 2048)
        else:
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 1024)
    except Exception as e:
        logging.error(f"容量计算异常: {str(e)}")
        return 0

# 修改calculate路由
@app.route('/api/calculate', methods=['POST'])
def calculate():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '缺少文件'}), 400
        
        file = request.files['file']
        if not allowed_media_file(file.filename):
            return jsonify({'error': '不支持的媒体文件类型'}), 400
        
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        
        try:
            file.save(temp_path)
            
            capacity = get_capacity(temp_path)
            return jsonify({
                'filename': file.filename,
                'capacity': capacity,
                'human_readable': f"{capacity} 字节 (约 {capacity/1024/1024:.1f} MB)"
            })
        finally:
            try:
                os.remove(temp_path)
            except:
                pass
                
    except Exception as e:
        logging.error(f"容量计算错误: {str(e)}")
        return jsonify({'error': str(e), 'capacity': 0}), 500

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.errorhandler(404)
def page_not_found(e):
    return send_from_directory('templates', '404.html'), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000, host="0.0.0.0", threaded=True)

# 定义文件头签名映射
FILE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': '.png',
    b'\xff\xd8\xff': '.jpg',
    b'BM': '.bmp',
    b'ID3': '.mp3',
    b'RIFF': {
        b'WAVE': '.wav',
        b'AVI ': '.avi'
    },
    b'\x00\x00\x00\x14ftyp': {
        b'mp41': '.mp4',
        b'mp42': '.mp4',
        b'isom': '.mp4'
    },
    b'\x1a\x45\xdf\xa3': '.mkv'
}