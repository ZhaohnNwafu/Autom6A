import queue
import threading
import time
import json
from pathlib import Path

# ==================== 全局变量 ====================
log_queue = queue.Queue()
current_thread = None
stop_flag = threading.Event()
task_running = False
_task_start_time = None

# 任务状态文件
TASK_STATE_FILE = Path(".task_state.json")


def log_callback(message):
    """Agent日志回调"""
    timestamp = time.strftime("%H:%M:%S")
    log_queue.put(f"[{timestamp}]{message}")


def _format_elapsed_time():
    """格式化已运行时间"""
    global _task_start_time
    if _task_start_time is None:
        return "00:00:00"
    
    elapsed = int(time.time() - _task_start_time)
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _save_task_state(state):
    """保存任务状态到文件"""
    try:
        with open(TASK_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save task state: {e}")

def _clear_log_queue():
    """清空日志队列"""
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break

def init_task_state():
    """初始化任务状态"""
    global task_running, _task_start_time
    task_running = True
    _task_start_time = time.time()
    _clear_log_queue()

def reset_task_state():
    """重置任务状态"""
    global task_running, _task_start_time, current_thread, stop_flag
    task_running = False
    _task_start_time = None
    current_thread = None
    stop_flag.clear()

def set_current_thread(thread):
    """设置当前线程"""
    global current_thread
    current_thread = thread

def get_current_thread():
    """获取当前线程"""
    return current_thread

def is_task_running():
    """检查任务是否在运行"""
    return task_running

def get_stop_flag():
    """获取停止标志"""
    return stop_flag

def _stream_logs_with_heartbeat():
    """
    优化版日志流式输出 - 解决长时间任务假死问题
    """
    global current_thread, stop_flag, task_running, _task_start_time

    log_buffer = []
    MAX_DISPLAY_LINES = 100
    MAX_HISTORY_LINES = 500
    
    last_yield_time = time.time()
    last_heartbeat_time = time.time()
    last_save_time = time.time()
    
    MIN_YIELD_INTERVAL = 0.1
    HEARTBEAT_INTERVAL = 10
    SAVE_INTERVAL = 30
    
    line_count = 0
    
    # 主循环 - 持续检查线程状态和日志队列
    while True:
        current_time = time.time()
        has_new_log = False
        
        # 检查线程是否存在且活跃
        thread_alive = False
        if current_thread is not None:
            try:
                thread_alive = current_thread.is_alive()
            except Exception:
                thread_alive = False
        
        # 如果线程不活跃且日志队列为空，则退出循环
        if not thread_alive and log_queue.empty():
            # 等待一小段时间，以防有延迟的日志
            time.sleep(0.1)
            if log_queue.empty():
                break
        
        # 批量获取日志
        try:
            while not log_queue.empty():
                message = log_queue.get_nowait()
                log_buffer.append(message)
                has_new_log = True
                line_count += 1
                
                if len(log_buffer) > MAX_HISTORY_LINES:
                    log_buffer = log_buffer[-MAX_HISTORY_LINES:]
        except queue.Empty:
            pass
        
        # 心跳机制
        if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
            last_heartbeat_time = current_time
            has_new_log = True
        
        # 定期保存状态
        if current_time - last_save_time >= SAVE_INTERVAL:
            _save_task_state({
                'running': True,
                'line_count': line_count,
                'last_update': time.strftime("%Y-%m-%d %H:%M:%S")
            })
            last_save_time = current_time
        
        # 控制yield频率
        if has_new_log and (current_time - last_yield_time >= MIN_YIELD_INTERVAL):
            display_lines = log_buffer[-MAX_DISPLAY_LINES:]
            
            if len(log_buffer) > MAX_DISPLAY_LINES:
                truncated_count = len(log_buffer) - MAX_DISPLAY_LINES
                display_text = f"[...{truncated_count} earlier lines truncated for performance...]\n\n"
                display_text += '\n'.join(display_lines)
            else:
                display_text = '\n'.join(display_lines)
            
            # 添加实时统计
            stats = f"\n\n{'='*50}\n"
            stats += f"📊 总行数: {line_count} | 显示: {len(display_lines)} | "
            stats += f"运行时间: {_format_elapsed_time()} | "
            stats += f"状态: {'运行中' if current_thread and current_thread.is_alive() else '已完成'}"
            
            yield display_text + stats
            last_yield_time = current_time
        
        # 检查停止信号
        if stop_flag.is_set():
            log_buffer.append("\nℹ️ 停止信号已接收，正在终止任务...")
            display_text = '\n'.join(log_buffer[-MAX_DISPLAY_LINES:])
            yield display_text
            break
        
        time.sleep(0.05)
    
    # 任务结束后的最终输出
    while not log_queue.empty():
        try:
            message = log_queue.get_nowait()
            log_buffer.append(message)
            line_count += 1
        except queue.Empty:
            break
    
    # 最终显示
    display_lines = log_buffer[-MAX_DISPLAY_LINES:]
    if len(log_buffer) > MAX_DISPLAY_LINES:
        truncated_count = len(log_buffer) - MAX_DISPLAY_LINES
        final_text = f"[...{truncated_count} earlier lines truncated...]\n\n"
        final_text += '\n'.join(display_lines)
    else:
        final_text = '\n'.join(display_lines)
    
    if stop_flag.is_set():
        final_text += "\n\n✅ 任务已停止\n"
    else:
        final_text += f"\n\n🎉 任务完成！共处理 {line_count} 行日志\n"
    
    _save_task_state({
        'running': False,
        'completed': True,
        'line_count': line_count,
        'end_time': time.strftime("%Y-%m-%d %H:%M:%S")
    })
    
    task_running = False
    
    yield final_text