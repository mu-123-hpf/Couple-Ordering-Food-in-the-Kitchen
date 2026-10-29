# 情侣厨房 · Couple Kitchen

一个只属于两个人的点单小厨房：一方下单小心意，另一方接单、完成。包含响应式的 Web 应用（Python 标准库 HTTP + SQLite，无第三方依赖）和 Android WebView 客户端（可打包成 APK）。手机与电脑访问同一个服务地址，共享同一份菜单和订单。

> 本仓库为脱敏公开版本：服务器地址、域名与真实数据均已移除或替换为占位符（域名 `kitchen.example.com`，服务器 IP `203.0.113.10`，Android 包名 `com.example.lovekitchen`）。部署到你自己的服务器时，请把这些占位符替换成你自己的实际值。

## 功能

- 双账号体系：PBKDF2-SHA256（600,000 次迭代）加盐密码、哈希化会话令牌、CSRF 校验、登录限流
- 订单归属由服务端判定：自己不能接自己的单，只有收到的一方可以接单和完成
- 14 个分类、60 道菜谱（含配图），支持新增 / 编辑 / 删除、随机选菜、搜索
- 手机 / PC 响应式界面；订单页面自动刷新同步
- SQLite 单文件存储，支持在线导出 JSON 备份
- Android 客户端：原生 WebView、图片选择、备份导出、断网重试；不绕过 TLS 校验、无 JS 原生桥

## 本地运行

要求：Python 3.10+，无需任何第三方依赖。

```bash
python couple_kitchen.py --app
```

启动后打开 http://127.0.0.1:8765/ ，终端会打印初始化口令文件的位置（`kitchen_app/data/kitchen.setup-token.txt`）；用该口令一次性创建两个账号，成功后口令失效，不能再注册第三个账号。数据默认保存在 `kitchen_app/data/kitchen.sqlite3`（已 gitignore）。

无副作用自检（不启动服务器、使用临时数据库）：

```bash
python couple_kitchen.py --app --check
```

其他参数：`--host`（默认仅本机，可信局域网可设 `0.0.0.0`）、`--port`（默认 8765）、`--data`（自定义数据库路径）。

## 测试

```bash
python tests/verify_accounts.py
```

集成测试使用临时数据库、无副作用（49 项：双账号隔离、订单权限、菜单与设置同步）；结果写入 `kitchen_app/records/`。

## Android 客户端

源码在 `android/` 目录。内置的服务地址在 `android/config.json` 的 `baseUrl` 和 `MainActivity.java` 的 `BASE_URL` 里，两者必须保持一致。构建需要 JDK 和 Android SDK（build-tools 35、platform android-35）：

```bash
python android/build_apk.py
```

首次构建会在 `android/signing/` 生成签名密钥（已 gitignore）。升级 APK 必须沿用同一密钥，请离线妥善备份，不要上传到任何公开位置。

## 部署（可选）

`deploy/` 提供 Linux + Nginx + systemd 的部署模板：

- `couple-kitchen.service` — systemd 服务（监听 127.0.0.1:8765，启用 `KITCHEN_SECURE_COOKIE=1`，`KITCHEN_PUBLIC_ORIGIN` 指向你的 HTTPS 域名）
- `couple-kitchen-https.conf` / `couple-kitchen-http.conf` — Nginx 站点与证书配置，使用前把其中的占位域名替换为你自己的域名
- 数据文件和用户上传图片放在服务用户的可写目录，不要放在代码目录里

生产环境务必经 HTTPS 反向代理对外服务，并始终将数据库与上传的图片一起备份。

## 项目结构

```
couple_kitchen.py        入口（--app 启动双人厨房 Web 应用）
kitchen_app/
  server.py              HTTP 服务、路由、订单与菜单逻辑
  auth.py                双账号、密码与会话
  seed.json              默认菜单与分类
  static/                前端页面与配图
  records/               测试结果
android/                 Android WebView 客户端源码与构建脚本
deploy/                  部署模板
tests/                   集成测试
```

## 安全设计（摘要）

- 密码：PBKDF2-SHA256、每账号随机盐、600k 迭代；连续失败 15 分钟限流
- 会话：随机令牌仅以哈希存库；Cookie 为 HttpOnly + SameSite=Strict（生产环境加 Secure）
- 写请求：CSRF 令牌 + Origin / Sec-Fetch-Site 校验
- 订单状态机（pending → accepted → completed）由服务器仲裁
- 上传仅接受 500KB 以内的 JPEG；静态资源做目录越界校验

## 许可

本仓库未附许可协议，保留所有权利。如需公开许可，请自行添加 LICENSE 文件。
