document.addEventListener('DOMContentLoaded', function() {
    // 标签页切换
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            
            // 更新按钮状态
            tabBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // 更新内容区域
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
        });
    });
    
    // 拖放功能
    setupDropZone('media-drop-zone', 'media-input', handleMediaFile);
    setupDropZone('data-drop-zone', 'data-input', handleDataFile);
    setupDropZone('decode-drop-zone', 'decode-input', handleDecodeFile);
    
    // 编码按钮
    document.getElementById('encode-btn').addEventListener('click', encodeData);
    
    // 解码按钮
    document.getElementById('decode-btn').addEventListener('click', decodeData);
});

function setupDropZone(dropZoneId, inputId, fileHandler) {
    const dropZone = document.getElementById(dropZoneId);
    const fileInput = document.getElementById(inputId);
    
    dropZone.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', e => {
        if (e.target.files.length) {
            fileHandler(e.target.files[0]);
        }
    });
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    dropZone.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        dropZone.classList.add('highlight');
    }
    
    function unhighlight() {
        dropZone.classList.remove('highlight');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        fileHandler(file);
    }
}

let selectedMediaFile = null;
let selectedDataFile = null;
let selectedDecodeFile = null;

function handleMediaFile(file) {
    selectedMediaFile = file;
    updateFileInfo('media-drop-zone', file.name);
    calculateCapacity(file)
        .then(() => checkEncodeButton())
        .catch(() => {});
}

// 添加缺失的handleDataFile函数
function handleDataFile(file) {
    selectedDataFile = file;
    updateFileInfo('data-drop-zone', file.name);
    // 更新数据大小显示
    document.getElementById('data-size').textContent = file.size;
    document.getElementById('data-readable').textContent = formatBytes(file.size);
    checkEncodeButton();
}

// 添加字节转换函数
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 修改容量计算回调
// 修改calculateCapacity函数
function calculateCapacity(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    return fetch('/api/calculate', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                try {
                    const err = JSON.parse(text);
                    throw new Error(err.error || '计算容量失败');
                } catch {
                    throw new Error(text || '服务器返回非JSON响应');
                }
            });
        }
        return response.json();
    })
    .then(data => {
        // 添加这部分代码来更新UI显示
        document.getElementById('capacity-info').textContent = data.capacity;
        document.getElementById('capacity-readable').textContent = formatBytes(data.capacity);
        return data;
    })
    .catch(error => {
        console.error('计算容量错误:', error);
        showStatus('计算容量失败: ' + error.message, 'error');
        throw error;
    });
}

// 修改其他fetch请求也添加类似错误处理
// 修改encodeData函数，确保正确发送请求
function encodeData() {
    if (!selectedMediaFile || !selectedDataFile) {
        showStatus('请先选择媒体文件和数据文件', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('media', selectedMediaFile);
    formData.append('data', selectedDataFile);
    
    showStatus('正在隐藏数据...', 'info');
    
    fetch('/api/encode', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { 
                throw new Error(err.error || '编码失败'); 
            });
        }
        return response.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = selectedMediaFile.name;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        showStatus('数据隐藏成功!', 'success');
    })
    .catch(error => {
        showStatus('隐藏数据失败: ' + error.message, 'error');
        console.error('编码错误:', error);
    });
}

// 修复解码页面拖动上传问题
function handleDecodeFile(file) {
    selectedDecodeFile = file;
    updateFileInfo('decode-drop-zone', file.name);
    document.getElementById('decode-btn').disabled = false;
}

// 修改decodeData函数中使用插件的方式
// 在文件顶部添加导入语句
import { detectFileType } from './plugin/file-type-detector.js';

function decodeData() {
    if (!selectedDecodeFile) return;
    
    const formData = new FormData();
    formData.append('media', selectedDecodeFile);
    
    showStatus('正在提取数据...', 'info');
    
    fetch('/api/decode', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error); });
        }
        return response.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        // 修改为直接判断提取出来的blob数据
        return detectFileTypeFromBlob(blob)
            .then(ext => {
                const a = document.createElement('a');
                a.href = url;
                a.download = 'extracted_data' + ext;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                showStatus('数据提取成功!', 'success');
            });
    })
    .catch(error => {
        showStatus('提取数据失败: ' + error.message, 'error');
    });
}

// 新增函数：直接从Blob判断文件类型
function detectFileTypeFromBlob(blob) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            const buffer = e.target.result;
            const view = new Uint8Array(buffer);
            const header = Array.from(view.slice(0, 8)).map(b => b.toString(16).padStart(2, '0')).join('');
            
            // 常见文件类型的文件头签名
            const signatures = {
                'ffd8ffe0': '.jpg',    // JPEG
                '89504e47': '.png',    // PNG
                '47494638': '.gif',    // GIF
                '424d': '.bmp',        // BMP
                '504b0304': '.zip',    // ZIP
                '52617221': '.rar',    // RAR
                '377abcaf': '.7z',     // 7Z
                '25504446': '.pdf',    // PDF
                'd0cf11e0': '.doc',    // DOC
                '504b34': '.docx',     // DOCX
                '494433': '.mp3',      // MP3
                '52494646': '.wav',    // WAV
                '664c6143': '.flac',   // FLAC
                '00000020': '.mp4',    // MP4
                '52494646': '.avi',    // AVI
                '1a45dfa3': '.mkv'     // MKV
            };

            // 检查文件头匹配
            for (const sig in signatures) {
                if (header.startsWith(sig)) {
                    return resolve(signatures[sig]);
                }
            }

            // 默认返回.dat
            resolve('.dat');
        };

        // 读取blob前8字节
        reader.readAsArrayBuffer(blob.slice(0, 8));
    });
}

function showStatus(message, type) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status ' + type;
}


function updateFileInfo(dropZoneId, filename) {
    const dropZone = document.getElementById(dropZoneId);
    dropZone.querySelector('p').textContent = filename;
}

function checkEncodeButton() {
    const btn = document.getElementById('encode-btn');
    btn.disabled = !(selectedMediaFile && selectedDataFile);
}
