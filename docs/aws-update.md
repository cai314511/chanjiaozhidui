# AWS更新与三端演示空间

本地实现不会直接修改云服务器。把本次代码、`data/demo-reference/`、`web/demo-portfolio/`一起更新到服务器，再使用现有服务管理方式重启。保留服务器原有`.env`和`data/private/`；不要从本机复制账户数据库或替换持久数据目录。

## 本次版本包含什么

- 高校培养诊断改为图文报告，含五项评价、三情景、四年曲线、能力与资源图、具体课程调整建议。
- 全校XLSX课表支持多个校区工作表、字段别名和标题行，按课程代码归并教学班，支持本校课程搜索及XLSX导出。
- 三端助手的输入、语音和发送按钮保持可见，资料授权独立展开。
- 招聘数据字典、学历与经验映射、公告去重及对应参考包一并更新。

这一版本不需要新增数据库表或执行账号初始化。已有用户数据继续保存在 `data/private/`。不要为更新而运行 `scripts/initialize.py`。

## EC2 Linux：按现有部署更新

下面适用于已经部署本项目的Ubuntu / Amazon Linux实例；命令在服务器终端执行。将项目目录、服务名换成服务器实际值。若使用Docker，阅读后面的容器说明，不在宿主机另外启动Python服务。

### 1. 连接实例，确认项目目录和启动方式

可在EC2控制台选择实例 → **连接** → 使用已配置的EC2 Instance Connect、Session Manager或SSH。SSH用户名由实例系统决定，Ubuntu通常为`ubuntu`，Amazon Linux通常为`ec2-user`，以控制台显示的连接命令为准。

```bash
cd /你的实际项目目录/chanjiaozhidui
pwd
git remote -v
git status --short --branch
systemctl list-units --type=service --all | grep -Ei 'chanjiao|chanzhi|chanjiaozhidui|uvicorn'
pgrep -af 'scripts/serve.py|uvicorn|gunicorn'
```

如果找到了systemd服务，记下服务名，并核对其工作目录和启动路径：

```bash
SERVICE_NAME='实际服务名.service'
systemctl show "$SERVICE_NAME" -p WorkingDirectory -p ExecStart -p User
```

服务名和项目路径均不能根据本机目录猜测。如果Git显示服务器有已跟踪文件改动，先核对并另行保存这些修改，解决后再继续；不要使用强制覆盖命令。

### 2. 停止现有应用，备份服务器配置和数据

systemd部署执行：

```bash
sudo systemctl stop "$SERVICE_NAME"
BACKUP_DIR="$HOME/chanjiaozhidui-backups/$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$BACKUP_DIR"
git rev-parse HEAD > "$BACKUP_DIR/commit.txt"
if [ -f .env ]; then install -m 600 .env "$BACKUP_DIR/.env"; fi
if [ -d data/private ]; then cp -a data/private "$BACKUP_DIR/private"; fi
printf '本次备份目录：%s\n' "$BACKUP_DIR"
```

确认备份命令没有报错再继续。数据可能包含用户文件和体验空间，需预留对应磁盘空间。备份目录放在仓库外；如有独立文件挂载，也按原部署方式备份。手动启动的应用应先通过原终端Ctrl+C或原进程管理方式停止，再执行备份，不使用批量杀进程命令。

### 3. 拉取main并安装到服务器原有虚拟环境

```bash
git pull --ff-only origin main
git log -1 --oneline
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Linux虚拟环境通常为`.venv/bin/python`；如果第1步显示服务用的是其他Python路径，沿用那个环境。不要复制Windows的`.venv`到Linux。`git pull --ff-only`失败时先处理分支或本地修改，不继续重启。

### 4. 修改项目配置

项目根目录已有`.env`时直接编辑；仅当不存在时才从模板创建：

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
nano .env
```

没有`nano`时使用服务器现有编辑器。至少确认：

```dotenv
DEEPSEEK_API_KEY=在服务器编辑器中填写你的真实密钥
DEEPSEEK_MODEL=deepseek-flash
```

项目会读取根目录`.env`。**进程中同名环境变量优先于`.env`**：如果systemd、Docker或原启动脚本已经设置了旧值，需在原配置位置同步修改，避免文件改了但进程仍使用旧值。不要把真实密钥写入Git、截图或聊天记录。

鉴权检查可先执行：

```bash
.venv/bin/python scripts/check_deepseek.py
```

需要验证一次实际生成时，再执行以下命令，会使用少量API额度：

```bash
.venv/bin/python scripts/check_deepseek.py --call
```

若密钥只配置在服务进程环境中，独立终端不会自动继承，应按该环境的原检查方式验证。健康接口的`agent_configured`仅表示配置非空，不代表调用成功。

### 5. 重启原服务并检查日志

```bash
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
sudo journalctl -u "$SERVICE_NAME" -n 60 --no-pager
```

仅修改项目`.env`或拉取代码不需要`daemon-reload`。如果修改了systemd服务文件或drop-in，先执行`sudo systemctl daemon-reload`，再重启。正常运行应沿用原有`WorkingDirectory`、服务用户、虚拟环境和端口。

如果原来就是手动启动，先确认旧实例已停止，在项目目录运行：

```bash
.venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8765
```

此命令在前台运行，关闭SSH会话可能导致服务退出；持续运行应沿用原有systemd / 进程管理机制。仅在原部署直接对外开放8765且确实需要保持该方式时，使用`--host 0.0.0.0`。Linux不使用`--background`，该启动器的后台与进程核验逻辑面向Windows本地预览。

### 6. 验收接口和浏览器

```bash
curl --fail --silent --show-error http://127.0.0.1:8765/api/health
curl --fail --silent --show-error http://127.0.0.1:8765/api/demo/status
curl --silent --output /dev/null --write-out '%{http_code}\n' http://127.0.0.1:8765/
```

随后打开原来的域名或公网地址，强制刷新（Windows浏览器`Ctrl+F5`），进入高校端：

1. “高校培养诊断”出现新报告、五项评价和三情景按钮。
2. 有已保存专业决策时可切换四年匹配度、就业率、招生规模；缺资料时展示缺项。
3. 在目标高校账号上传全校课表，查看工作表、归并数量和冲突提示，并测试课程库搜索与导出。
4. 三端右下角助手打开后，文字、语音和发送按钮无需向下滚动即可操作。

如果本机接口200但公网不可访问，再检查原反向代理、实例安全组和监听端口；沿用现有域名与HTTPS配置，不必为本次界面更新新开端口。

## Docker部署的区别

先运行`docker compose config --services`确认实际服务名。按原Compose配置备份数据库挂载卷和环境文件，再在仓库目录执行`git pull --ff-only origin main`及`docker compose up -d --build 实际服务名`，随后用`docker compose logs --tail=60 实际服务名`检查。核实`.env`中需要的变量确实通过`environment`或`env_file`传入应用，持久数据挂载仍指向原位置；Compose读取`.env`用于变量替换，并不等于全部变量自动传入容器。本仓库未提供Dockerfile/Compose模板，需沿用服务器已有配置。

## 语音与已有参考数据

- XLSX导入、诊断图表、四年决策计算不依赖DeepSeek Key；只有模型助手调用需要有效配置。
- Whisper识别需要服务器上的完整模型目录，并通过进程环境配置`CHZ_WHISPER_MODEL`。`backend/voice.py`不单独读取`.env`中的这个变量；systemd可使用原服务的`EnvironmentFile`，手动运行可先`export CHZ_WHISPER_MODEL=/实际模型目录`。浏览器麦克风权限通常要求HTTPS或localhost；公网HTTP下可能只能打字。Windows SAPI语音合成不能直接用于Linux，云端不会因拉取代码自动获得Windows语音能力。
- 新版参考包会随Git更新，但应用只为缺失的固定公共记录补齐数据，不覆盖云端已存在的聚合。更新代码不会重算历史数据。服务器若持有两份原始CSV，需要刷新全行业目录或高校需求时，可按原流程分别执行`.venv/bin/python scripts/import_market.py`和`.venv/bin/python scripts/import_demand.py`，缺少默认路径时用`--csv`显式指定；脚本各自先备份。不要把公告条数当招聘人数，也不要把本机账号库复制到云端。

连接实例参考：[AWS EC2官方文档](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-linux-instance.html)。systemd命令可在服务器通过`man systemctl`核对。

## 环境及启动

1. 使用服务器原有Python虚拟环境安装`requirements.txt`。
2. 在服务器本地`.env`中配置`DEEPSEEK_API_KEY`和`DEEPSEEK_MODEL=deepseek-flash`。密钥仅留在服务器，不进入Git。
3. 执行`python scripts/check_deepseek.py --call`，验证鉴权、模型ID和一次极短生成；HTTP健康状态的“已配置”只说明读取到了非空密钥。
4. 复用现有systemd、容器或进程管理配置重启应用。直接对8765端口提供服务时，可执行`python scripts/serve.py --host 0.0.0.0 --port 8765`。通过反向代理提供服务时继续绑定127.0.0.1。不要同时启动两个实例争抢同一端口。
5. 验证`/api/health`、`/`、`/api/demo/status`均正常。未登录首页应出现“免登录体验三端”，进入后可切换三种角色。

首次启动为缺少比赛资料的正式数据库补齐参考包中的固定公共记录，不覆盖已有版本。若需要更新既有市场聚合，使用原有比赛资料导入脚本及其备份流程。

## 演示数据与交互

每个浏览器获得随机、不可枚举的体验凭证，对应`data/private/demo/<随机凭证>/`中的独立SQLite及文件目录。正式登录Cookie保持不变；退出演示后恢复原来的正式身份。演示控制端点不允许切换管理员。

同一浏览器三端共享当前空间里的岗位、投递、收藏、会话和培养记录。刷新或退出后重新进入可继续体验；“重置体验”创建全新空间并回收原体验空间，不删除正式数据。

凭证有效期7天，单进程最多缓存3个子应用；空间总数上限100，创建新空间时自动回收已过期目录。每个来源IP每分钟最多创建2次、每小时10次，每浏览器每小时最多重置3次。超额时返回明确提示，不会删除仍在有效期内的其他访客空间。也可通过`python scripts/cleanup_demo.py --dry-run`预览，再用`--apply`清理。清理只操作经过路径校验且带有效空间清单的过期目录，不触碰正式数据库。多进程部署时建议采用单应用进程或为演示元数据改用数据库协调；当前空间控制锁为进程内锁。

每空间每小时最多20次助手执行，限额覆盖对话、面试等走统一Agent入口的调用。该限制用于体验流量控制，不能替代云服务账户额度管理。

## 验收路径

- 企业：招聘总览 → 岗位管理 → 学生主页/候选人 → 主页与简历 → 收藏 → 联系 → 私信。
- 学生：能力画像/个人主页 → 岗位 → 投递并授权资料 → 消息中心回复。
- 高校：需求研判 → 培养诊断 → 课程资料 → 培养方案优化 → 专业调整决策。
- 退出演示后核对正式账号、岗位、文件及私信未被体验操作修改；用另一浏览器进入，核对两个体验空间互相独立。

页面中市场数据标注历史观察期和来源；人物经历、课程方案及业务记录只存在隔离体验空间。预置计算结果由真实匹配与优化引擎计算；配置有效密钥后助手调用真实DeepSeek接口。
