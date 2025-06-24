import requests
import logging
import time
import os
import threading
import json
from datetime import datetime
from config import TG_BOT_TOKEN, TG_CHAT_ID, SUBSCRIBE_PASSWORD, DEFAULT_USER_SETTINGS, USER_SETTINGS_FILE, TIMEFRAMES, MAX_MSG_LEN
from utils import ensure_file_exists

USER_FILE = "allowed_users.txt"
file_lock = threading.Lock()

def safe_write_user(user_id):
    """安全写入用户ID到文件"""
    with file_lock:
        if not os.path.exists(USER_FILE):
            with open(USER_FILE, "w") as f:
                f.write(user_id + "\n")
            os.chmod(USER_FILE, 0o600)
        else:
            with open(USER_FILE, "a") as f:
                f.write(user_id + "\n")

def load_user_settings():
    ensure_file_exists(USER_SETTINGS_FILE)
    try:
        with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"加载用户设置失败: {e}")
        return {}

def save_user_settings(settings):
    try:
        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        logging.error(f"保存用户设置失败: {e}")

def get_user_settings(user_id):
    user_id = str(user_id)
    settings = load_user_settings()
    return settings.get(user_id, DEFAULT_USER_SETTINGS.copy())

def update_user_settings(user_id, setting_type, value):
    user_id = str(user_id)
    settings = load_user_settings()
    if user_id not in settings:
        settings[user_id] = DEFAULT_USER_SETTINGS.copy()
    if setting_type == "timeframes":
        timeframes = [tf.strip() for tf in value.split(",") if tf.strip() in TIMEFRAMES]
        if timeframes:
            settings[user_id]["enabled_timeframes"] = timeframes
    elif setting_type == "signals":
        signals = [s.strip() for s in value.split(',') if s.strip()]
        settings[user_id]["enabled_signals"] = signals
    save_user_settings(settings)

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

def send_long_telegram_message(text):
    for i in range(0, len(text), MAX_MSG_LEN):
        send_to_allowed_users(text[i:i+MAX_MSG_LEN])

def should_send_signal(user_id, signal):
    settings = get_user_settings(user_id)
    # 时间周期过滤
    if signal.get("timeframe") not in settings.get("enabled_timeframes", []):
        return False
    # 信号类型过滤
    if signal.get("type") not in settings.get("enabled_signals", []):
        return False
    return True
    
def send_to_allowed_users(msg):
    users = load_allowed_users()
    for user_id in users:
        send_message(user_id, msg)

def handle_signals(sig, rsi6_signals, can_biao_xiu_signals):
    users = load_allowed_users()
    for user_id in users:
        if sig["type"] == "rsi6_extreme" and should_send_signal(user_id, sig):
            rsi6_signals.append(sig)
        elif sig["type"] == "can_biao_xiu" and should_send_signal(user_id, sig):
            can_biao_xiu_signals.append(sig)
        elif should_send_signal(user_id, sig):
            msg = format_signal(sig)
            send_message(user_id, msg)

def format_signal(sig):
    """格式化信号为可读消息"""
    if sig["type"] == "turtle_buy":
        return (
            f"[海龟交易法] {sig['symbol']} {sig['timeframe']} 发现买入信号\n"
            f"时间    : {sig['time']}\n"
            f"开盘价  : {sig['open']}\n"
            f"收盘价  : {sig['close']}\n"
            f"MA200   : {sig['ma200']}\n"
            f"DC中轨  : {sig['mid']}\n"
        )
    elif sig["type"] == "turtle_sell":
        return (
            f"[海龟交易法] {sig['symbol']} {sig['timeframe']} 发现卖出信号\n"
            f"时间    : {sig['time']}\n"
            f"开盘价  : {sig['open']}\n"
            f"收盘价  : {sig['close']}\n"
            f"MA200   : {sig['ma200']}\n"
            f"DC中轨  : {sig['mid']}\n"
        )
    elif sig["type"] == "five_down":
        return (
            f"[五连阴] {sig['symbol']} {sig['timeframe']} 发现五连阴卖出信号\n"
            f"时间    : {sig['time']}\n"
            f"最近5根K线收盘价: {', '.join(map(str, sig['closes']))}\n"
            f"最近5根K线开盘价: {', '.join(map(str, sig['opens']))}\n"
        )
    elif sig["type"] == "rsi6_extreme":
        return (
            f"[RSI6极值] {sig['symbol']} {sig['timeframe']}\n"
            f"值 : {sig['rsi6']:.2f}\n"
            f"时间 : {sig['time']}\n"
        )
    else:
        logging.warning(f"未知信号类型: {sig['type']}")
        return f"未知信号类型: {sig['type']}"

    # 汇总推送RSI6极值
def rsi6_summary(signals):
    signals.sort(key=lambda x: x['rsi6'], reverse=True)
    table = f"{'交易对':<18}{'周期':<7}{'RSI6':<7}\n"
    table += f"{'-'*18}{'-'*7}{'-'*7}\n"
    for s in signals:
        table += f"{s['symbol']:<20}{s['timeframe']:<8}{s['rsi6']:<8.2f}\n"
    send_long_telegram_message(f"RSI6极值信号汇总：\n```\n{table}```")
        
    # 汇总推送参标修信号
def send_can_biao_xiu_signals(signals, df_cache):
    table = f"{'交易对':<8}{'信号':<4}{'时间':<10}\n"
    table += f"{'-'*10}{'-'*4}{'-'*16}\n"
    for sig in signals:
        df = df_cache.get((sig['symbol'], sig['timeframe']))
        if df is None:
            continue
        can_time = str(df['timestamp'].iloc[sig['can_idx']])[:10]
        table += f"{sig['symbol']:<10}{'参':<4}{can_time:<16}\n"
        if sig['biao_idx'] is not None:
            biao_time = str(df['timestamp'].iloc[sig['biao_idx']])[:10]
            table += f"{sig['symbol']:<10}{'标':<4}{biao_time:<16}\n"
        if sig['xiu_idx'] is not None:
            xiu_time = str(df['timestamp'].iloc[sig['xiu_idx']])[:10]
            table += f"{sig['symbol']:<10}{'修':<4}{xiu_time:<16}\n"
    msg = f"参的低点是标的压力位\n标的低点是修的压力位\n修的低点是最强支撑位\n\n日线级别参标修信号汇总：\n```\n{table}```"
    send_long_telegram_message(msg)

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
                    if text.startswith("/unsubscribe"):
                        if remove_user(user_id):
                            known_users.remove(user_id)
                            send_message(user_id, "您已成功退订推送。")
                            logging.info(f"用户{user_id}退订成功")
                        else:
                            send_message(user_id, "退订失败，您可能未订阅。")
                            logging.warning(f"用户{user_id}退订失败，未在订阅列表")
                        continue
                    elif text.startswith("/settings"):
                        settings = get_user_settings(user_id)
                        msg = (
                            f"当前设置：\n"
                            f"启用时间周期: {', '.join(settings.get('enabled_timeframes', []))}\n"
                            + escape_markdown(f"启用信号类型: {', '.join(settings.get('enabled_signals', []))}")+ "\n\n"
                            "PS: 参标修仅启用日线可用，五连阴仅识别BTC，ETH交易对\n\n"
                            "修改设置示例:\n"
                            + escape_markdown("/set_timeframes 1h,4h,1d") + "\n"
                            + escape_markdown("/set_signals turtle_buy,turtle_sell,five_down") + "\n"
                        )
                        send_message(user_id, msg)
                    elif text.startswith("/set_timeframes"):
                        try:
                            timeframes = text.split(' ',1)[1]
                            update_user_settings(user_id, "timeframes", timeframes)
                            send_message(user_id, f"启用的时间周期已更新为：{timeframes}")
                        except:
                            send_message(user_id, escape_markdown("用法：/set_timeframes 1h,4h,1d"))
                    elif text.startswith("/set_signals"):
                        try:
                            signals = text.split(' ',1)[1]
                            update_user_settings(user_id, "signals", signals)
                            send_message(user_id, "启用信号类型已更新")
                        except:
                            send_message(user_id, escape_markdown("用法: /set_signals rsi6_extreme,turtle_buy,turtle_sell,can_biao_xiu,five_down"))
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
                        send_message(user_id, "欢迎关注本机器人，您已成功订阅推送！\n使用/settings查看当前设置")
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

def escape_markdown(text):
    escape_chars = r'_*\[\]()~`>#+-=|{}.!'
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

def set_bot_commands():
    commands = [
        {"command": "settings", "description": "查看当前通知设置"},
        {"command": "set_timeframes", "description": "设置接收时间周期(逗号分隔)"},
        {"command": "set_signals", "description": "设置接收信号类型(逗号分隔)"},
        {"command": "unsubscribe", "description": "退订推送"},
        {"command": "adduser", "description": "管理员：手动添加用户"},
        {"command": "removeuser", "description": "管理员：手动移除用户"},
    ]
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/setMyCommands"
    data = {"commands": str(commands).replace("'", '"')}
    try:
        resp = requests.post(url, data=data)
        logging.info(f"设置机器人命令返回: {resp.text}")
    except Exception as e:
        logging.error(f"设置机器人命令异常: {e}")
