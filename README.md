## MediaSteganographyTools
使用此工具隐藏信息到媒体文件中，基于Python和html。

![image](https://github.com/user-attachments/assets/5b156b28-9052-4e64-98b3-7e3113d55f5c)
![image](https://github.com/user-attachments/assets/93abb4fb-823d-4cac-9056-af98f42a2c92)

项目使用了[这些库](https://github.com/liang-work/MediaSteganographyTools/blob/main/requirements.txt)，需要使用`pip install requirements.txt`进行安装。

可以上传这些文件：`png jpg jpeg bmp tiff mp3 wav flac m4a mp4 avi mov mkv`作为载体文件。可以上传任意格式的隐藏数据文件。

## 注意：如果载体文件被社交媒体压缩或修改，可能导致数据丢失。

---------------------------------

Q:为什么图片可用大小那么小？

A:因为图片使用的是SLB隐写，将数据写入像素，实际能用的就只有（图片高x图片宽x3）//8（字节）可以使用，看着大而已，而音频、视频用的是老式的尾部追加，所以可能十分接近原文件大小。

Q:为什么信息提取出来显示错误？

A:可能文件不是原文件，被压缩过，导致数据丢失。

Q:工具提供加密数据服务吗？

A:没有的，只是隐藏文件数据而已。

Q:可以隐藏哪些文件？

A:理论上任何小于计算的最大值的文件都可以，不论格式。

----------------------------------

代码使用AI编写
