import requests
import logging
import time
import os
import threading
from config import TG_BOT_TOKEN, TG_CHAT_ID, SUBSCRIBE_PASSWORD

USER_FILE = "allowed_users.txt"
file_lock = threading.Lock()

def safe_write_user(user_id):
    """安全写入用户ID到文件，首次创建文件设置权限"""
    with file_lock:
        if not os.path.exists(USER_FILE):
            with open(USER_FILE, "w") as f:
                f.write(user_id + "\n")
            os.chmod(USER_FILE, 0o600)
        else:
            with open(USER_FILE, "a") as f:
                f.write(user_id + "\n")

def load_allowed_users():
    """读取已授权用户集合"""
    with file_lock:
        if not os.path.exists(USER_FILE):
            return set()
        with open(USER_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())

def remove_user(user_id):
    """从文件中安全移除用户"""
    with file_lock:
        if not os.path.exists(USER_FILE):
            return False
        try:
            with open(USER_FILE, "r") as f:
                users = [line.strip() for line in f if line.strip()]
            if user_id not in users:
                return False
            users.remove(user_id)
            with open(USER_FILE, "w") as f:
                for u in users:
                    f.write(u + "\n")
            os.chmod(USER_FILE, 0o600)
            return True
        except Exception as e:
            logging.error(f"移除用户{user_id}时文件操作异常: {e}")
            return False

def send_message(chat_id, text):
    """统一发送消息接口，含异常处理"""
    if not TG_BOT_TOKEN or not chat_id:
        logging.error("TG_BOT_TOKEN 或 chat_id 未设置")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            logging.error(f"发送消息失败给{chat_id}: {resp.text}")
    except Exception as e:
        logging.error(f"发送消息异常给{chat_id}: {e}")

def send_telegram_message(text):
    """发送消息给管理员"""
    send_message(TG_CHAT_ID, text)

def send_to_allowed_users(text):
    """推送消息给所有已授权用户"""
    users = load_allowed_users()
    for user_id in users:
        send_message(user_id, text)

def monitor_new_users():
    """轮询监听新用户消息，处理订阅、退订、管理员命令"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    last_update_id = None
    known_users = load_allowed_users()
    pending_users = {}  # user_id -> [错误次数, 首次错误时间或锁定时间]

    while True:
        try:
            params = {"timeout": 10}
            if last_update_id:
                params["offset"] = last_update_id + 1
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            for update in data.get("result", []):
                last_update_id = update["update_id"]
                message = update.get("message")
                if not message:
                    continue
                user = message["from"]
                user_id = str(user["id"])
                username = user.get("username", "")
                text = message.get("text", "").strip()
                logging.info(f"收到用户{user_id}消息: {text}")

                # 管理员命令处理
                if user_id == str(TG_CHAT_ID):
                    if text.startswith("/adduser "):
                        target_id = text.split(" ", 1)[1].strip()
                        if target_id and target_id not in known_users:
                            safe_write_user(target_id)
                            known_users.add(target_id)
                            send_message(user_id, f"已手动添加用户 {target_id}")
                        else:
                            send_message(user_id, f"用户 {target_id} 已存在或无效")
                        continue
                    elif text.startswith("/removeuser "):
                        target_id = text.split(" ", 1)[1].strip()
                        if target_id and target_id in known_users:
                            if remove_user(target_id):
                                known_users.remove(target_id)
                                send_message(user_id, f"已手动移除用户 {target_id}")
                            else:
                                send_message(user_id, f"移除用户 {target_id} 失败")
                        else:
                            send_message(user_id, f"用户 {target_id} 不存在")
                        continue

                # 已授权用户不需重复订阅
                if user_id in known_users:
                    # 支持退订命令
                    if text.lower() == "/unsubscribe":
                        if remove_user(user_id):
                            known_users.remove(user_id)
                            send_message(user_id, "您已成功退订推送。")
                            logging.info(f"用户{user_id}退订成功")
                        else:
                            send_message(user_id, "退订失败，您可能未订阅。")
                            logging.warning(f"用户{user_id}退订失败，未在订阅列表")
                        continue
                    # 其他消息可忽略或自定义
                    continue

                # 非授权用户处理订阅密码逻辑
                # 锁定判断
                if user_id in pending_users and pending_users[user_id][0] >= 3:
                    # 判断是否锁定中
                    if time.time() - pending_users[user_id][1] < 3600:
                        # 仍锁定中，忽略消息
                        continue
                    else:
                        # 解锁，重置计数
                        pending_users[user_id] = [0, time.time()]

                if user_id not in pending_users:
                    # 第一次提示输入密码
                    send_message(user_id, "请输入订阅密码：")
                    pending_users[user_id] = [0, time.time()]
                    continue

                # 已提示过密码，判断输入
                if text == SUBSCRIBE_PASSWORD:
                    if user_id not in known_users:
                        safe_write_user(user_id)
                        known_users.add(user_id)
                        send_telegram_message(f"添加新用户：{username} (ID: {user_id})")
                        send_message(user_id, "欢迎关注本机器人，您已成功订阅推送！")
                    pending_users.pop(user_id, None)
                elif text.lower() == "/unsubscribe":
                    # 未订阅用户退订提示
                    send_message(user_id, "您尚未订阅，无需退订。")
                else:
                    # 密码错误，增加错误次数
                    pending_users[user_id][0] += 1
                    if pending_users[user_id][0] >= 3:
                        # 锁定一小时
                        send_message(user_id, "错误次数过多，请1小时后再试。")
                        pending_users[user_id][1] = time.time()
                    else:
                        send_message(user_id, "密码错误，请重新输入订阅密码：")

        except Exception as e:
            logging.error(f"监听新用户异常: {e}", exc_info=True)
        time.sleep(10)  # 轮询间隔

def set_bot_commands():
    """设置机器人命令，方便用户和管理员操作"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/setMyCommands"
    commands = [
        {"command": "unsubscribe", "description": "退订推送"},
        {"command": "adduser", "description": "管理员：手动添加用户"},
        {"command": "removeuser", "description": "管理员：手动移除用户"},
    ]
    data = {"commands": str(commands).replace("'", '"')}
    try:
        resp = requests.post(url, data=data)
        logging.info(f"设置机器人命令返回: {resp.text}")
    except Exception as e:
        logging.error(f"设置机器人命令异常: {e}")