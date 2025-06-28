import time
from flask import Flask, request, jsonify, send_file, send_from_directory
import os
import logging
from werkzeug.utils import secure_filename
from datetime import datetime
import tempfile
from PIL import Image
import numpy as np
from decimal import Decimal, getcontext
#from flask_uploads import UploadSet, configure_uploads, ALL

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB限制

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
    # 读取载体图片并确保RGB模式
    img = Image.open(media_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img_array = np.array(img)
    
    # 读取要隐藏的数据
    with open(data_path, 'rb') as f:
        data = f.read()
    
    # 添加数据长度前缀(4字节)和校验和(4字节)
    data_len = len(data)
    checksum = sum(data) & 0xFFFFFFFF  # 32位校验和
    data_with_header = data_len.to_bytes(4, 'big') + checksum.to_bytes(4, 'big') + data
    
    # 使用Decimal计算容量
    total_pixels = Decimal(img_array.size)
    required_pixels = Decimal(len(data_with_header)) * Decimal(8) / Decimal(3)
    
    if required_pixels > total_pixels:
        raise ValueError(f"需要{required_pixels}像素，但图片只有{total_pixels}像素")
    
    # 使用NumPy批量处理LSB嵌入
    data_bits = np.unpackbits(np.frombuffer(data_with_header, dtype=np.uint8))
    flat_array = img_array.reshape(-1, 3)
    
    for i in range(len(data_bits)):
        channel = i % 3
        pixel = i // 3
        flat_array[pixel, channel] = (flat_array[pixel, channel] & 0xFE) | data_bits[i]
    
    # 保存为PNG格式确保无损
    Image.fromarray(flat_array.reshape(img_array.shape)).save(output_path, format='PNG')

def lsb_decode(media_path, output_path):
    # 读取含密图片并确保RGB模式
    img = Image.open(media_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img_array = np.array(img)
    
    # 使用Decimal计算最大容量
    total_bits = Decimal(img_array.size) * Decimal(3)
    available_bits = total_bits - Decimal(64)  # 减去64位头
    
    # 提取所有LSB位
    lsb_bits = (img_array & 1).flatten()
    
    # 提取数据长度和校验和(8字节头)
    if len(lsb_bits) < 64:
        raise ValueError("数据头不完整")
    
    header_bytes = np.packbits(lsb_bits[:64]).tobytes()
    data_len = int.from_bytes(header_bytes[:4], 'big')
    expected_checksum = int.from_bytes(header_bytes[4:8], 'big')
    
    # 验证数据长度合理性
    max_capacity = (len(lsb_bits) - 64) // 8
    if data_len <= 0 or data_len > max_capacity:
        raise ValueError(f"无效数据长度: {data_len} (最大容量: {max_capacity}字节)")
    
    # 提取数据内容
    data_bits = lsb_bits[64:64+data_len*8]
    if len(data_bits) < data_len * 8:
        raise ValueError("数据不完整")
    
    extracted_data = np.packbits(data_bits).tobytes()
    
    # 验证校验和
    actual_checksum = sum(extracted_data) & 0xFFFFFFFF
    if actual_checksum != expected_checksum:
        # 添加调试信息
        logging.error(f"校验和验证失败: 头信息={header_bytes.hex()}")
        logging.error(f"提取数据长度: {len(extracted_data)}字节")
        logging.error(f"前16字节数据: {extracted_data[:16].hex()}")
        raise ValueError(f"校验和不匹配: 预期{expected_checksum}, 实际{actual_checksum}")
    
    # 写入文件
    with open(output_path, 'wb') as f:
        f.write(extracted_data)

# 文件尾隐写实现
def tail_encode(media_path, data_path, output_path):
    # 读取载体文件
    with open(media_path, 'rb') as f:
        media_data = f.read()
    
    # 读取要隐藏的数据
    with open(data_path, 'rb') as f:
        data = f.read()
    
    # 添加标记和数据长度前缀
    marker = b'STEGANO_MARKER'
    data_len = len(data).to_bytes(4, byteorder='big')
    combined_data = marker + data_len + data
    
    # 写入新文件
    with open(output_path, 'wb') as f:
        f.write(media_data)
        f.write(combined_data)

def tail_decode(media_path, output_path):
    # 读取含密文件
    with open(media_path, 'rb') as f:
        media_data = f.read()
    
    # 查找标记
    marker = b'STEGANO_MARKER'
    pos = media_data.rfind(marker)
    if pos == -1:
        raise ValueError("未找到隐藏数据")
    
    # 提取数据长度
    data_len = int.from_bytes(media_data[pos+len(marker):pos+len(marker)+4], byteorder='big')
    
    # 提取数据
    data_start = pos + len(marker) + 4
    data_end = data_start + data_len
    if data_end > len(media_data):
        raise ValueError("数据损坏或长度不正确")
    
    extracted_data = media_data[data_start:data_end]
    
    # 保存提取的数据
    with open(output_path, 'wb') as f:
        f.write(extracted_data)

# 修改文件类型验证部分
ALLOWED_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'mp3', 'wav', 'flac', 'm4a', 'mp4', 'avi', 'mov', 'mkv'}
# 移除ALLOWED_DATA_EXTENSIONS限制

# 添加插件接口装饰器
def stegano_plugin(func):
    """隐写插件装饰器"""
    func.is_stegano_plugin = True
    return func

# 修改encode路由
# 替换Flask-Uploads相关代码
@app.route('/api/encode', methods=['POST'])
def encode():
    try:
        if 'media' not in request.files or 'data' not in request.files:
            return jsonify({'error': '缺少必要文件'}), 400
        
        media_file = request.files['media']
        data_file = request.files['data']
        
        # 使用原生Flask文件处理
        media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
        data_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(data_file.filename))
        
        # 只验证媒体文件类型
        if not allowed_media_file(media_file.filename):
            return jsonify({'error': '不支持的媒体文件类型'}), 400
        
        # 保存临时文件
        media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
        data_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(data_file.filename))
        media_file.save(media_path)
        data_file.save(data_path)
        
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

# 添加文件类型识别插件
@stegano_plugin
def detect_file_type(file_path):
    """自动识别文件类型并返回合适的扩展名"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)  # 读取文件头
        
        # 常见文件类型的魔数签名
        signatures = {
            b'\x50\x4B\x03\x04': '.zip',
            b'\x52\x61\x72\x21': '.rar',
            b'\x37\x7A\xBC\xAF': '.7z',
            b'\x25\x50\x44\x46': '.pdf',
            b'\xD0\xCF\x11\xE0': '.doc',
            b'\x50\x4B\x03\x04\x14\x00\x06\x00': '.docx',
            b'\xFF\xD8\xFF\xE0': '.jpg',
            b'\x89\x50\x4E\x47': '.png',
            b'\x47\x49\x46\x38': '.gif',
            b'\x49\x44\x33': '.mp3',
            b'\x52\x49\x46\x46': '.wav',
            b'\x66\x4C\x61\x43': '.flac',
            b'\x00\x00\x00\x20\x66\x74\x79\x70': '.mp4',
            b'\x1A\x45\xDF\xA3': '.mkv',
            b'\x52\x49\x46\x46': '.avi'
        }
        
        for sig, ext in signatures.items():
            if header.startswith(sig):
                return ext
                
        # 纯文本检测
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read()
            return '.txt'
        except:
            return '.dat'
            
    except Exception as e:
        logging.error(f"文件类型识别错误: {str(e)}")
        return '.dat'

# 修改decode路由以使用插件
@app.route('/api/decode', methods=['POST'])
def decode():
    try:
        if 'media' not in request.files:
            return jsonify({'error': '缺少媒体文件'}), 400
        
        media_file = request.files['media']
        
        if not allowed_media_file(media_file.filename):
            return jsonify({'error': '不支持的媒体文件类型'}), 400
        
        # 保存媒体文件
        media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
        media_file.save(media_path)
        
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
            
            # 确保文件存在
            if not os.path.exists(output_path):
                raise FileNotFoundError("解码后文件未生成")
            
            # 读取文件内容到内存
            with open(output_path, 'rb') as f:
                file_data = f.read()
            
            # 创建响应对象
            response = app.response_class(
                response=file_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename=extracted_data{ext}',
                    'Content-Type': 'application/octet-stream'
                }
            )
            
            # 清理临时文件
            if os.path.exists(media_path):
                os.remove(media_path)
            if os.path.exists(output_path):
                os.remove(output_path)
                
            logging.info(f"解码成功: {media_file.filename} -> extracted_data{ext}")
            return response
            
        except Exception as e:
            # 清理可能残留的文件
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(media_path):
                os.remove(media_path)
            raise e
            
    except Exception as e:
        logging.error(f"解码错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 修改容量计算函数名，避免与路由冲突
# 修改文件大小限制
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 提高到100MB

# 修改get_capacity函数
def get_capacity(media_path):
    try:
        if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            # 对于图片文件，计算LSB隐写容量
            with Image.open(media_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                width, height = img.size
                # 每个像素3个通道，每个通道1位，8位=1字节
                return (width * height * 3) // 8
        elif media_path.lower().endswith(('.mp3', '.wav', '.flac', '.m4a')):
            # 对于音频文件，计算文件尾隐写容量
            # 返回文件大小减去1KB的头部空间
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 1024)
        elif media_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            # 对于视频文件，计算文件尾隐写容量
            # 返回文件大小减去2KB的头部空间
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 2048)
        else:
            # 其他文件类型，返回文件大小减去1KB
            file_size = os.path.getsize(media_path)
            return max(0, file_size - 1024)
    except Exception as e:
        logging.error(f"容量计算异常: {str(e)}")
        return 0

# 修改calculate路由，移除media_upload依赖
@app.route('/api/calculate', methods=['POST'])
def calculate():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '缺少文件'}), 400
        
        file = request.files['file']
        if not allowed_media_file(file.filename):
            return jsonify({'error': '不支持的媒体文件类型'}), 400
        
        # 创建临时文件路径
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        
        try:
            # 保存文件
            file.save(temp_path)
            
            capacity = get_capacity(temp_path)
            return jsonify({
                'filename': file.filename,
                'capacity': capacity,
                'human_readable': f"{capacity} 字节 (约 {capacity/1024/1024:.1f} MB)"
            })
        finally:
            # 确保删除临时文件
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
    app.run(debug=True, port=5000, host="0.0.0.0")