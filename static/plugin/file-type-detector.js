/**
 * 文件类型检测插件
 * 直接通过文件头判断文件类型
 */
export function detectFileType(file) {
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
                '424d': '.bmp',         // BMP
                '504b0304': '.zip',    // ZIP
                '52617221': '.rar',    // RAR
                '377abcaf': '.7z',      // 7Z
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

        // 读取文件前8字节
        reader.readAsArrayBuffer(file.slice(0, 8));
    });
}
