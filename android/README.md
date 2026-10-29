# 情侣厨房 Android 客户端

内置地址：https://kitchen.example.com/ 。APK 与 PC/手机浏览器使用同一后端数据库；登录同一账号即可看到相同订单、菜单和设置，会话分别保存，不复制浏览器 Cookie。

- 原生 WebView 加载真实 HTTPS 页面，不内嵌脱离服务器的离线网页。
- Android 7.0+（minSdk 24），targetSdk 35；包含图片选择、确认对话框、返回、连接重试和 JSON 备份导出。
- 不绕过证书校验，不允许明文 HTTP，不内置 SSH/数据库密码；不开启 JS 原生桥。
- 需要设备联网，断网时明确显示重试页面；同一账号的订单页面每10秒刷新。

构建：`python D:\xbb\android\build_apk.py`。官方 SDK 位于 `D:\xbb\work\android-sdk`，JDK 使用本机 JAVA_HOME。
产物：`D:\xbb\out\couple-kitchen-1.0.0.apk`。
签名私钥与口令在 android/signing/，不上传至公开下载目录；升级必须保留并使用同一签名密钥。
本地构建会检查签名和清单。设备实际安装及触控体验需真实 Android 设备；未连接设备时不得声称已验证安装。
