import requests
import logging
import time
import os
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # 过滤掉rsi6_extreme，因为它是必选的
        signals = [s.strip() for s in value.split(',') if s.strip() and s.strip() != "rsi6_extreme"]
        settings[user_id]["enabled_signals"] = signals
    save_user_settings(settings)

def load_allowed_users():
    """读取已授权用户集合"""
    with file_lock:
        if not os.path.exists(USER_FILE):
            return set()
        with open(USER_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())

def get_user_info(user_id):
    """获取用户的Telegram信息"""
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getChat"
        params = {"chat_id": user_id}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                chat = data.get("result", {})
                username = chat.get("username", "无用户名")
                first_name = chat.get("first_name", "")
                last_name = chat.get("last_name", "")
                full_name = f"{first_name} {last_name}".strip() or "无姓名"
                return {
                    "username": username,
                    "full_name": full_name,
                    "user_id": user_id
                }
    except Exception as e:
        logging.error(f"获取用户{user_id}信息失败: {e}")
    
    return {
        "username": "获取失败",
        "full_name": "获取失败", 
        "user_id": user_id
    }

def check_and_clean_blocked_users():
    """检查并清理被屏蔽的用户"""
    users = list(load_allowed_users())
    blocked_users = []
    
    for user_id in users:
        try:
            # 尝试发送一个测试消息（使用getChat API更轻量）
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getChat"
            params = {"chat_id": user_id}
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code != 200:
                response_data = resp.json()
                error_code = response_data.get("error_code", 0)
                description = response_data.get("description", "")
                
                # 检查是否是用户屏蔽或账户被停用
                if error_code == 403 and ("bot was blocked by the user" in description or 
                                         "user is deactivated" in description or
                                         "Forbidden: user not found" in description):
                    blocked_users.append(user_id)
                    logging.info(f"发现被屏蔽/停用的用户: {user_id}")
        except Exception as e:
            logging.error(f"检查用户 {user_id} 状态异常: {e}")
    
    # 移除被屏蔽的用户
    removed_count = 0
    for user_id in blocked_users:
        if remove_user(user_id):
            removed_count += 1
            logging.info(f"已移除被屏蔽的用户: {user_id}")
    
    return removed_count, len(blocked_users)

def list_all_users():
    """列出所有订阅用户的信息"""
    users = list(load_allowed_users())
    if not users:
        return "📋 当前没有订阅用户"
    
    msg = f"📋 订阅用户列表 (共{len(users)}人)\n\n"
    
    for i, user_id in enumerate(users, 1):
        user_info = get_user_info(user_id)
        settings = get_user_settings(user_id)
        
        # 格式化信号类型，使其更简洁
        timeframes = settings.get('enabled_timeframes', [])
        signals = settings.get('enabled_signals', [])
        
        # 简化信号名称显示，排除RSI6(必选项)
        signal_names = []
        for signal in signals:
            if signal == "turtle_buy":
                signal_names.append("🐢买")
            elif signal == "turtle_sell":
                signal_names.append("🐢卖") 
            elif signal == "can_biao_xiu":
                signal_names.append("📊参标修")
            elif signal == "five_down":
                signal_names.append("📉五连阴")
            # 跳过rsi6_extreme，因为它是必选的，不显示在可选列表中
        
        # 使用简单的文本格式，避免复杂的Markdown
        msg += f"{i}. {user_info['full_name']} (@{user_info['username']})\n"
        msg += f"   用户ID: {user_id}\n"
        msg += f"   周期: {', '.join(timeframes) if timeframes else '未设置'}\n"
        msg += f"   必选信号: RSI6\n"
        msg += f"   可选信号: {', '.join(signal_names) if signal_names else '无'}\n\n"
    
    return msg

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
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    # 检查是否是用户列表消息，如果是则使用纯文本模式
    if text.startswith("📋 订阅用户列表"):
        data = {
            "chat_id": chat_id,
            "text": text
        }
    else:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            response_data = resp.json()
            error_code = response_data.get("error_code", 0)
            description = response_data.get("description", "")
            
            # 检查是否是用户屏蔽机器人的错误
            if error_code == 403 and ("bot was blocked by the user" in description or "user is deactivated" in description):
                logging.warning(f"用户 {chat_id} 已屏蔽机器人，自动移除该用户")
                # 自动移除被屏蔽的用户
                if remove_user(str(chat_id)):
                    logging.info(f"已自动移除被屏蔽的用户: {chat_id}")
                    # 通知管理员
                    if str(chat_id) != str(TG_CHAT_ID):
                        send_telegram_message(f"⚠️ 用户 {chat_id} 已屏蔽机器人，已自动移除订阅")
                else:
                    logging.error(f"移除被屏蔽用户 {chat_id} 失败")
                return False
            else:
                logging.error(f"发送消息失败给{chat_id}: {resp.text}")
                return False
        return True
    except Exception as e:
        logging.error(f"发送消息异常给{chat_id}: {e}")
        return False

def send_plain_message(chat_id, text):
    """发送纯文本消息（不使用Markdown解析）"""
    if not TG_BOT_TOKEN or not chat_id:
        logging.error("TG_BOT_TOKEN 或 chat_id 未设置")
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    data = {
        "chat_id": chat_id,
        "text": text
        # 不设置 parse_mode，默认为纯文本
    }
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            response_data = resp.json()
            error_code = response_data.get("error_code", 0)
            description = response_data.get("description", "")
            
            # 检查是否是用户屏蔽机器人的错误
            if error_code == 403 and ("bot was blocked by the user" in description or "user is deactivated" in description):
                logging.warning(f"用户 {chat_id} 已屏蔽机器人，自动移除该用户")
                # 自动移除被屏蔽的用户
                if remove_user(str(chat_id)):
                    logging.info(f"已自动移除被屏蔽的用户: {chat_id}")
                    # 通知管理员
                    if str(chat_id) != str(TG_CHAT_ID):
                        send_telegram_message(f"⚠️ 用户 {chat_id} 已屏蔽机器人，已自动移除订阅")
                else:
                    logging.error(f"移除被屏蔽用户 {chat_id} 失败")
                return False
            else:
                logging.error(f"发送纯文本消息失败给{chat_id}: {resp.text}")
                return False
        return True
    except Exception as e:
        logging.error(f"发送纯文本消息异常给{chat_id}: {e}")
        return False

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
    
def send_message_async(chat_id, text):
    """异步发送单条消息的包装函数"""
    return send_message(chat_id, text)

def send_to_allowed_users(msg):
    """并发发送消息给所有授权用户"""
    users = list(load_allowed_users())
    if not users:
        return
    
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    # 根据用户数量动态调整线程池大小
    max_workers = min(50, max(1, len(users)))
    
    # 使用线程池并发发送消息
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="msg_send") as executor:
        # 提交所有发送任务
        future_to_user = {
            executor.submit(send_message_async, user_id, msg): user_id 
            for user_id in users
        }
        
        # 收集结果
        for future in as_completed(future_to_user):
            user_id = future_to_user[future]
            try:
                result = future.result(timeout=15)  # 15秒超时
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logging.error(f"发送消息给用户 {user_id} 异常: {e}")
    
    elapsed_time = time.time() - start_time
    logging.info(f"批量发送完成: 成功 {success_count}/{len(users)}, 失败 {failed_count}, 耗时: {elapsed_time:.2f}秒")

def send_pinned_message_to_all(msg):
    """发送置顶消息给所有授权用户"""
    users = list(load_allowed_users())
    if not users:
        logging.warning("没有订阅用户，无法发送置顶消息")
        return
    
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    # 根据用户数量动态调整线程池大小
    max_workers = min(50, max(1, len(users)))
    
    # 使用线程池并发发送置顶消息
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pin_send") as executor:
        # 提交所有发送任务
        future_to_user = {
            executor.submit(send_pinned_message_async, user_id, msg): user_id 
            for user_id in users
        }
        
        # 收集结果
        for future in as_completed(future_to_user):
            user_id = future_to_user[future]
            try:
                result = future.result(timeout=20)  # 20秒超时（置顶需要更多时间）
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logging.error(f"发送置顶消息给用户 {user_id} 异常: {e}")
    
    elapsed_time = time.time() - start_time
    logging.info(f"置顶消息发送完成: 成功 {success_count}/{len(users)}, 失败 {failed_count}, 耗时: {elapsed_time:.2f}秒")

def send_pinned_message_async(chat_id, text):
    """异步发送置顶消息（使用纯文本模式，不转义）"""
    try:
        # 发送纯文本消息（不使用Markdown解析）
        message_sent = send_plain_message(chat_id, text)
        if not message_sent:
            return False
        
        # 获取刚发送的消息ID来置顶（需要bot有管理员权限）
        # 注意：只有在群组中且bot有置顶权限时才能置顶
        # 私聊中无法置顶消息，所以这里只是发送消息
        return True
        
    except Exception as e:
        logging.error(f"发送置顶消息给 {chat_id} 异常: {e}")
        return False

def send_to_allowed_users_serial(msg):
    """原始的串行发送方式（保留作为备用）"""
    users = load_allowed_users()
    for user_id in users:
        send_message(user_id, msg)

def handle_signals(sig, rsi6_signals):
    """处理信号发送，对符合条件的用户发送信号"""
    # RSI6信号只收集用于汇总，不单独发送
    if sig["type"] == "rsi6_extreme":
        rsi6_signals.append(sig)
        return
    
    # 为其他信号类型收集需要发送的用户
    users = list(load_allowed_users())
    target_users = []
    
    for user_id in users:
        if should_send_signal(user_id, sig):
            target_users.append(user_id)
    
    # 如果有目标用户，使用并发发送
    if target_users:
        msg = format_signal(sig)
        send_to_target_users_concurrent(target_users, msg)

def send_to_target_users_concurrent(target_users, msg):
    """并发发送消息给指定的用户列表"""
    if not target_users:
        return
    
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    # 根据用户数量动态调整线程池大小
    max_workers = min(8, max(1, len(target_users)))
    
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="signal_send") as executor:
        future_to_user = {
            executor.submit(send_message_async, user_id, msg): user_id 
            for user_id in target_users
        }
        
        for future in as_completed(future_to_user):
            user_id = future_to_user[future]
            try:
                result = future.result(timeout=10)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logging.error(f"发送信号给用户 {user_id} 异常: {e}")
    
    elapsed_time = time.time() - start_time
    logging.debug(f"信号发送完成: 成功 {success_count}/{len(target_users)}, 失败 {failed_count}, 耗时: {elapsed_time:.2f}秒")

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
            f"开盘价  : {sig['open']:.6f}\n"
            f"收盘价  : {sig['close']:.6f}\n"
            f"MA200   : {sig['ma200']:.6f}\n"
            f"DC中轨  : {sig['mid']:.6f}\n"
        )
    elif sig["type"] == "five_down":
        return (
            f"[五连阴] {sig['symbol']} {sig['timeframe']} 发现五连阴卖出信号\n"
            f"时间    : {sig['time']}\n"
            f"最近5根K线收盘价: {', '.join([f'{x:.6f}' for x in sig['closes']])}\n"
            f"最近5根K线开盘价: {', '.join([f'{x:.6f}' for x in sig['opens']])}\n"
        )
    elif sig["type"] == "rsi6_extreme":
        msg = (
            f"[RSI6极值] {sig['symbol']} {sig['timeframe']}\n"
            f"值 : {sig['rsi6']:.2f}\n"
            f"时间 : {sig['time']}\n"
        )
        
        # 如果有RSI预测信息，添加到消息中
        if 'prediction_type' in sig and sig['prediction_type'] is not None:
            if sig['prediction_type'] == "bottom":
                msg += (
                    f"📉 RSI接针预测:\n"
                    f"当前价格: {sig['current_price']:.2f}\n"
                    f"预测底部: {sig['predicted_bottom']:.2f}\n"
                    f"预计跌幅: {sig['potential_drop']:.2f}\n"
                    f"RSI斜率: {sig['rsi_slope']:.2f}\n"
                )
            elif sig['prediction_type'] == "top":
                msg += (
                    f"📈 RSI顶部预测:\n"
                    f"当前价格: {sig['current_price']:.2f}\n"
                    f"预测顶部: {sig['predicted_top']:.2f}\n"
                    f"预计涨幅: {sig['potential_rise']:.2f}\n"
                    f"RSI斜率: {sig['rsi_slope']:.2f}\n"
                )
        
        return msg
    elif sig["type"] == "can_biao_xiu":
        msg = f"[参标修] {sig['symbol']}\n"
        msg += f"参信号时间: {sig.get('can_time', '-')}\n"
        msg += f"标信号时间: {sig.get('biao_time', '-')}\n"
        msg += f"修信号时间: {sig.get('xiu_time', '-')}\n"
        return msg
    else:
        logging.warning(f"未知信号类型: {sig['type']}")
        return f"未知信号类型: {sig['type']}"

    # 汇总推送RSI6极值
def rsi6_summary(signals):
    signals.sort(key=lambda x: x['rsi6'], reverse=True)
    
    # 检查是否有预测信息
    has_predictions = any('prediction_type' in s and s['prediction_type'] is not None for s in signals)
    
    if has_predictions:
        # 包含预测信息的简化表格
        table = f"{'币种':<8}{'周期':<4}{'RSI6':<6}{'当前价格':<12}{'预测价格':<12}\n"
        table += f"{'-'*8}{'-'*4}{'-'*6}{'-'*12}{'-'*12}\n"
        for s in signals:
            if 'prediction_type' in s and s['prediction_type'] is not None:
                if s['prediction_type'] == "bottom":
                    predicted_price = s.get('predicted_bottom', 0)
                elif s['prediction_type'] == "top":
                    predicted_price = s.get('predicted_top', 0)
                else:
                    predicted_price = 0
                
                # 根据价格大小动态调整格式，使其更易读
                if s['current_price'] >= 100:
                    # 大于100的价格，保留整数
                    current_fmt = f"{s['current_price']:.0f}"
                    predicted_fmt = f"{predicted_price:.0f}"
                elif s['current_price'] >= 1:
                    # 1到100之间，保留2位小数
                    current_fmt = f"{s['current_price']:.2f}"
                    predicted_fmt = f"{predicted_price:.2f}"
                elif s['current_price'] >= 0.01:
                    # 0.01到1之间，保留4位小数
                    current_fmt = f"{s['current_price']:.4f}"
                    predicted_fmt = f"{predicted_price:.4f}"
                elif s['current_price'] >= 0.0001:
                    # 0.0001到0.01之间，保留6位小数
                    current_fmt = f"{s['current_price']:.6f}"
                    predicted_fmt = f"{predicted_price:.6f}"
                else:
                    # 极小价格，保留8位小数
                    current_fmt = f"{s['current_price']:.8f}"
                    predicted_fmt = f"{predicted_price:.8f}"
                
                table += f"{s['symbol']:<8}{s['timeframe']:<4}{s['rsi6']:<6.1f}{current_fmt:<12}{predicted_fmt:<12}\n"
            else:
                # 无预测信息的行
                if s.get('current_price', 0) >= 100:
                    current_fmt = f"{s.get('current_price', 0):.0f}" if 'current_price' in s else "--"
                elif s.get('current_price', 0) >= 1:
                    current_fmt = f"{s.get('current_price', 0):.2f}" if 'current_price' in s else "--"
                elif s.get('current_price', 0) >= 0.01:
                    current_fmt = f"{s.get('current_price', 0):.4f}" if 'current_price' in s else "--"
                elif s.get('current_price', 0) >= 0.0001:
                    current_fmt = f"{s.get('current_price', 0):.6f}" if 'current_price' in s else "--"
                else:
                    current_fmt = f"{s.get('current_price', 0):.8f}" if 'current_price' in s and s['current_price'] > 0 else "--"
                
                table += f"{s['symbol']:<8}{s['timeframe']:<4}{s['rsi6']:<6.1f}{current_fmt:<12}{'--':<12}\n"
    else:
        # 原始简化表格
        table = f"{'币种':<12}{'周期':<6}{'RSI6':<8}\n"
        table += f"{'-'*12}{'-'*6}{'-'*8}\n"
        for s in signals:
            table += f"{s['symbol']:<12}{s['timeframe']:<6}{s['rsi6']:<8.1f}\n"
    
    send_long_telegram_message(f"RSI6极值信号汇总：\n```\n{table}```")

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
                    elif text == "/listusers":
                        user_list_msg = list_all_users()
                        send_message(user_id, user_list_msg)
                        continue
                    elif text == "/cleanblocked":
                        removed_count, total_blocked = check_and_clean_blocked_users()
                        # 重新加载用户列表以同步
                        known_users = load_allowed_users()
                        send_message(user_id, f"🧹 清理完成！\n发现被屏蔽用户: {total_blocked} 人\n成功移除: {removed_count} 人")
                        continue
                    elif text.startswith("/pin "):
                        # 发送置顶消息给所有用户
                        pin_message = text.split(" ", 1)[1].strip()
                        if pin_message:
                            send_pinned_message_to_all(pin_message)
                            send_message(user_id, f"消息已发送给所有用户")
                        else:
                            send_message(user_id, "请提供要置顶的消息内容")
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
                        
                        # 显示可选信号类型
                        optional_signals = settings.get('enabled_signals', [])
                        optional_signal_names = []
                        for signal in optional_signals:
                            if signal == "turtle_buy":
                                optional_signal_names.append("🐢买")
                            elif signal == "turtle_sell":
                                optional_signal_names.append("🐢卖")
                            elif signal == "can_biao_xiu":
                                optional_signal_names.append("📊参标修")
                            elif signal == "five_down":
                                optional_signal_names.append("📉五连阴")
                            # 跳过rsi6_extreme，因为它是必选的
                        
                        msg = (
                            f"当前设置：\n"
                            f"启用时间周期: {', '.join(settings.get('enabled_timeframes', []))}\n"
                            f"必选信号类型: RSI6 (自动启用)\n"
                            f"可选信号类型: {', '.join(optional_signal_names) if optional_signal_names else '无'}\n\n"
                            "PS: RSI6对所有用户必选，参标修仅启用日线可用，五连阴仅识别BTC交易对\n\n"
                            "修改设置示例:\n"
                            + escape_markdown("/set_timeframes 1h,4h,1d") + "\n"
                            + escape_markdown("/set_signals turtle_buy,turtle_sell,five_down") + "\n"
                            "注意: RSI6信号无需手动设置，系统自动为所有用户启用\n"
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
                            send_message(user_id, escape_markdown("用法: /set_signals turtle_buy,turtle_sell,can_biao_xiu,five_down"))
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
        {"command": "unsubscribe", "description": "退订推送"},
        {"command": "settings", "description": "查看当前通知设置"},
        {"command": "set_timeframes", "description": "设置接收时间周期(逗号分隔)"},
        {"command": "set_signals", "description": "设置接收信号类型(逗号分隔)"},
        {"command": "adduser", "description": "管理员：手动添加用户"},
        {"command": "removeuser", "description": "管理员：手动移除用户"},
        {"command": "listusers", "description": "管理员：查看所有订阅用户"},
        {"command": "cleanblocked", "description": "管理员：清理被屏蔽的用户"},
        {"command": "pin", "description": "管理员：发送置顶消息给所有用户"},
    ]
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/setMyCommands"
    data = {"commands": str(commands).replace("'", '"')}
    try:
        resp = requests.post(url, data=data)
        logging.info(f"设置机器人命令返回: {resp.text}")
    except Exception as e:
        logging.error(f"设置机器人命令异常: {e}")
