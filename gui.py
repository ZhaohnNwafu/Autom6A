import gradio as gr
import os
import threading
import time, sys, json
from src.agent import Agent
from src.intelligent_chat_handler import IntelligentChatHandler
import signal, os
from pathlib import Path 

# 导入日志处理模块
from src.log_handler import (
     log_queue, log_callback, init_task_state, reset_task_state,
    _stream_logs_with_heartbeat, _save_task_state,
    set_current_thread, is_task_running, get_stop_flag
)

# ========================== 工具函数 ==========================

def validate_quick_inputs(files_text, output_text, goal_text,data_type):
    """验证快速模式输入"""
    errors = []

    if not data_type:
        errors.append("❌ 请选择数据类型")

    if not files_text or not files_text.strip():
        errors.append("❌ 请输入数据文件路径")
    
    if not output_text or not output_text.strip():
        errors.append("❌ 请输入输出路径")
    
    if not goal_text or not goal_text.strip():
        errors.append("❌ 请描述分析目标")
    # Nanopore特殊检查：确保包含dorado路径
    if data_type == "Nanopore" and "dorado" not in files_text.lower():
        errors.append("⚠️ Nanopore数据分析需要提供dorado软件的绝对路径")
    
    return errors

# 辅助函数
def _parse_files_config(files_value):
    """解析文件配置为列表"""
    if isinstance(files_value, str):
        return [f.strip() for f in files_value.split('\n') if f.strip()]
    return files_value if isinstance(files_value, list) else [str(files_value)]

def _log_analysis_header(config, model, execute, mode, file_count):
    """输出分析开始的标准头部"""
    log_callback("="*50)
    log_callback(f"🚀 AutoM6A 智能分析系统 - {mode}")
    log_callback("="*50)
    log_callback(f"\n📊 配置信息:")
    log_callback(f"   物种: {config.get('species', 'N/A')}")
    log_callback(f"   数据类型: {config.get('data_type', 'N/A')}")
    log_callback(f"   数据文件数: {file_count}")
    log_callback(f"   输出目录: {config['output_dir']}")
    log_callback(f"   分析目标: {config['goal'][:100]}...")
    log_callback(f"\n⚙️ 执行设置:")
    log_callback(f"   模型: {model}")
    log_callback(f"   执行模式: {'真实执行' if execute else '仅生成代码'}")

def _log_success_footer(output_dir):
    """输出成功完成的标准尾部"""
    log_callback("\n" + "🎉"*20)
    log_callback("\n✅ 分析完成!")
    log_callback(f"\n📁 结果保存在: {output_dir}")
    log_callback("\n" + "🎉"*20)

#======================== 统一执行函数 ================================
def unified_analysis_executor(config, api_key, model_name, execute, mode_name="Analysis"):
    """统一的分析执行函数"""
    
    # 验证配置
    required_keys = ['files', 'output_dir', 'goal','data_type']
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        yield f"❌ 配置缺失: {', '.join(missing)}"
        return
    
    if not api_key or not api_key.strip():
        yield "❌ 请先设置API密钥"
        return
    
    if is_task_running():
        yield "⚠️ 已有任务在运行，请先停止当前任务"
        return
    
    # 初始化任务
    init_task_state()
    stop_flag = get_stop_flag()
    stop_flag.clear()
    
    _save_task_state({
        'running': True,
        'mode': mode_name,
        'start_time': time.strftime("%Y-%m-%d %H:%M:%S"),
        'config': config
    })
    
    files_list = _parse_files_config(config['files'])
    
    def run_agent():
        try:
            _log_analysis_header(config, model_name, execute, mode_name, len(files_list))
            
            # 根据数据类型设置RAG参数
            data_type = config.get('data_type', 'MeRIP-seq')
            use_rag = True  # 都使用RAG

            # 为Nanopore数据添加特殊标记
            if data_type == "Nanopore":
                log_callback("\n🔬 检测到Nanopore数据分析任务")
                log_callback("📚 将使用专门的Nanopore m6A分析流程知识库")
            
            agent = Agent(
                initial_data_list=files_list,
                output_dir=config['output_dir'],
                initial_goal_description=config['goal'],
                model_engine=model_name,
                openai_api=api_key.strip(),
                execute=execute,
                blacklist='STAR,java,perl,annovar',
                gui_mode=True,
                log_callback=log_callback,
                stop_flag=stop_flag,
                rag=use_rag,
                data_type=data_type,
            )
            
            if stop_flag.is_set():
                log_callback("⚠️ 任务在启动前被取消")
                return
            
            log_callback("="*50)
            log_callback("🚀 开始执行分析任务")
            log_callback("="*50)
            
            agent.run()
            
            if not stop_flag.is_set():
                _log_success_footer(config['output_dir'])
            else:
                log_callback("⚠️ 任务已被用户中断")
        
        except Exception as e:
            if stop_flag.is_set():
                log_callback("⚠️ 任务已中断")
            else:
                log_callback(f"❌ 错误: {e}")
                import traceback
                error_trace = traceback.format_exc()
                for line in error_trace.split('\n'):
                    if line.strip():
                        log_callback(line)
        finally:
            reset_task_state()
            log_callback("\n" + "="*50)
            log_callback("📌 Agent执行线程已结束")
            log_callback("="*50)
    
    # 启动执行线程
    thread = threading.Thread(target=run_agent, daemon=True)
    set_current_thread(thread)  # 关键：将线程对象设置到日志处理器
    thread.start()
    
    # 使用优化的日志流式输出
    yield from _stream_logs_with_heartbeat()

# ========================== Tab1: 智能对话模式 ============================
def initialize_handler(api_key, model_choice):
    """初始化智能对话处理器"""
    global intelligent_handler
    
    if not api_key or not api_key.strip():
        return [[None, "⚠️ 请先输入API密钥"]], gr.update(visible=False), "⚠️ 需要API密钥"
    
    model_name = model_choice

    try:
        print(f"[INFO] Initializing with model: {model_name}")
        intelligent_handler = IntelligentChatHandler(
            api_key=api_key.strip(),
            model_name=model_name
        )
        greeting = intelligent_handler.get_greeting()
        return [[None, greeting]], gr.update(visible=True), f"✅ 已连接 ({model_name})"
    except Exception as e:
        print(f"[ERROR] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return [[None, f"❌ 初始化失败: {str(e)}"]], gr.update(visible=False), f"❌ 初始化失败"

def chat_message(message, history, api_key, model_choice):
    """处理对话消息"""
    global intelligent_handler
    
    if intelligent_handler is None:
        if not api_key or not api_key.strip():
            return "", history, "⚠️ 请先设置API密钥并初始化", gr.update(visible=False)
        
        model_name = model_choice
        try:
            print(f"[INFO] Auto-initializing with model: {model_name}")
            intelligent_handler = IntelligentChatHandler(api_key.strip(), model_name)
        except Exception as e:
            print(f"[ERROR] Auto-initialization failed: {e}")
            return "", history, f"❌ 初始化失败: {str(e)}", gr.update(visible=False)
    
    if not message or not message.strip():
        return "", history, intelligent_handler.get_slots_display(), gr.update(visible=False)
    
    try:
        print(f"\n[GUI] Processing message: {message[:100]}...")
        ai_response, is_ready = intelligent_handler.process_message(message)
        print(f"[GUI] Is ready: {is_ready}")
        
        history = history + [[message, ai_response]]
        slots_info = intelligent_handler.get_slots_display()
        
        if is_ready:
            button_update = gr.update(visible=True, variant="primary")
        else:
            button_update = gr.update(visible=False)
        
        return "", history, slots_info, button_update
    
    except Exception as e:
        print(f"[ERROR] Exception in chat_message: {e}")
        import traceback
        traceback.print_exc()
        error_msg = f"❌ 处理出错: {str(e)}\n\n请重试或重新描述需求"
        history = history + [[message, error_msg]]
        return "", history, intelligent_handler.get_slots_display() if intelligent_handler else "", gr.update(visible=False)

def start_chat_analysis(history, api_key, model_choice, execute):
    """智能对话模式启动"""
    global intelligent_handler
    
    print(f"[GUI] start_chat_analysis called")
    if intelligent_handler is None:
        yield "❌ 助手未初始化，请先初始化"
        return
    
    if not intelligent_handler.is_ready():
        missing = intelligent_handler.slots.get_missing_required_slots()
        mapping = {"data_type": "数据类型", "files": "数据文件", "output_dir": "输出目录", "goal": "分析目标"}
        missing_names = [mapping.get(m, m) for m in missing]
        yield f"❌ 信息未收集完整，还缺少: {', '.join(missing_names)}"
        return
    
    config = intelligent_handler.get_config_for_agent()
    model_name = model_choice
    print(f"[GUI] Starting analysis with config: {config}")
    yield from unified_analysis_executor(config, api_key, model_name, execute, "智能对话模式")

def reset_chat(api_key, model_choice):
    """重置对话"""
    global intelligent_handler, stop_flag, task_running  
    print("[INFO] Resetting chat...")
    
    if is_task_running():
        stop_flag = get_stop_flag()
        stop_flag.set()
        time.sleep(1)
    
    if intelligent_handler:
        intelligent_handler.reset()
        greeting = intelligent_handler.get_greeting()
        return [[None, greeting]], "", "", gr.update(visible=False), "✅ 对话已重置"
    else:
        result = initialize_handler(api_key, model_choice)
        return result[0:1] + ("", "", gr.update(visible=False), result[2])

def start_new_conversation(api_key, model_choice):
    """开始新对话"""
    global intelligent_handler, stop_flag, task_running  
    print("[INFO] Starting new conversation...")
    
    if is_task_running():
        stop_flag = get_stop_flag()
        stop_flag.set()
        time.sleep(1)
    
    if intelligent_handler:
        intelligent_handler.reset()
        greeting = "🔄 已开始新对话！\n\n" + intelligent_handler.get_greeting()
        return [[None, greeting]], "", "", gr.update(visible=False), "✅ 新对话已开始"
    else:
        return initialize_handler(api_key, model_choice)[0:1] + ("", "", gr.update(visible=False), "✅ 新对话已开始")

def show_chat_examples():
    """显示智能对话示例"""
    examples = """### 💡 使用示例

**示例1 - 完整信息一次输入：**
```
我想分析拟南芥的m6A甲基化数据，文件在/data/merip目录，
有4个fastq文件，输出到/output，需要做质控、比对和peak calling
```

**示例2 - Nanopore三代测序：**
```
我有一些Nanopore三代测序的m6A数据，
fast5文件在/data/nanopore目录，
使用dorado做basecalling，然后检测m6A修饰位点，
输出到/output/nanopore_m6a
```
**💡 提示：**
- **Nanopore数据**：请明确提到"三代"、"Nanopore"或"fast5"
- **dorado路径**：必须提供dorado的完整路径"""
    return [[None, examples]]

# =========================== Tab2: 快速模式 ===============================
def generate_dorado_install_script():
    """生成dorado安装脚本"""
    script = """#!/bin/bash
# Dorado Basecalling Software Installation Script

set -e  # Exit on error

# Configuration
DORADO_VERSION="1.3.0"
INSTALL_DIR="${HOME}/software/dorado"
DOWNLOAD_URL="https://cdn.oxfordnanoportal.com/software/analysis/dorado-${DORADO_VERSION}-linux-x64.tar.gz"

# Create installation directory
mkdir -p ${INSTALL_DIR}
cd ${INSTALL_DIR}

# Download dorado
echo "Downloading dorado v${DORADO_VERSION}..."
wget -c -t 5 ${DOWNLOAD_URL} 

# Extract
echo "Extracting..."
tar -xzvf dorado-${DORADO_VERSION}-linux-x64.tar.gz

# Verify installation
echo "Verifying installation..."
./bin/dorado --version

# Print path
DORADO_PATH="${INSTALL_DIR}/bin/dorado"
echo "📍 Dorado executable path:"
echo "${DORADO_PATH}"
echo ""
echo "💡 Please add this path to your data files input:"
echo "${DORADO_PATH}: dorado basecaller executable"
"""
    return script

def on_data_type_change(data_type):
    """当数据类型改变时的回调"""
    if data_type == "Nanopore":
        # 生成安装脚本
        script = generate_dorado_install_script()
        
        # 准备提示信息
        warning_msg = """
⚠️ **Nanopore数据分析要求**

在开始分析前，请确保：

1. **安装dorado软件**
   - 已为您生成安装脚本（见下方）,将脚本保存为 `install_dorado.sh` 并执行
   - 或者如果已安装，请记录dorado的绝对路径

2. **在数据文件输入中添加dorado路径**
   - 示例：`/home/user/software/dorado/bin/dorado: dorado basecaller executable`

3. **确保有足够的GPU资源**
   - Dorado basecalling需要GPU加速
   - 建议使用NVIDIA GPU with CUDA support
"""
        return (
            gr.update(visible=True, value=warning_msg),  # warning box
            gr.update(visible=True, value=script),        # install script
            gr.update(value=load_nanopore_example()[0])  # update example
        )
    else:
        # m6A-seq/MeRIP-seq - 不需要特殊提示
        return (
            gr.update(visible=False, value=""),
            gr.update(visible=False, value=""),
            gr.update(value=load_merip_example()[0])
        )
    
def load_merip_example():
    """加载MeRIP-seq示例"""
    example_files = """/data/IP_rep1_R1.fastq.gz: IP sample 1 forward reads
/data/IP_rep1_R2.fastq.gz: IP sample 1 reverse reads
/data/Input_rep1_R1.fastq.gz: Input sample 1 forward reads
/data/Input_rep1_R2.fastq.gz: Input sample 1 reverse reads"""
    
    example_output = "/output/merip_analysis"
    
    example_goal = """Perform MeRIP-seq data analysis:
1. Quality control with FastQC
2. Alignment with HISAT2 to reference genome
3. Peak calling with MACS2
4. Differential methylation analysis"""
    
    return example_files, example_output, example_goal

def load_nanopore_example():
    """加载Nanopore示例"""
    example_files = """/home/user/software/dorado/bin/dorado: dorado basecaller executable
/data/nanopore/pod5_files/: directory containing POD5 raw data files
/reference/genome.fa: reference genome FASTA file
/reference/genome.fa.fai: reference genome index"""
    
    example_output = "/output/nanopore_m6a_analysis"
    
    example_goal = """Perform Nanopore direct RNA sequencing m6A modification analysis:
1. Basecalling with dorado using RNA004 model with modified base calling
2. Alignment to reference genome
3. m6A modification detection and quantification
4. Differential modification analysis"""
    
    return example_files, example_output, example_goal

def load_quick_example(data_type):
    """根据数据类型加载相应示例"""
    if data_type == "Nanopore":
        return load_nanopore_example()
    else:
        return load_merip_example()

def quick_start_analysis(data_type,input_files_text, output_path_text, goal_text, api_key, model_choice, execute):
    """快速模式启动"""
    print(f"[GUI] quick_start_analysis called with data_type={data_type}")
    errors = validate_quick_inputs(input_files_text, output_path_text, goal_text, data_type)
    if errors:
        yield "\n".join(errors)
        return
    
    # 检查API密钥
    if not api_key or not api_key.strip():
        yield "❌ 请先在配置区设置API密钥"
        return
    
    # 检查是否有任务在运行
    if is_task_running():
        yield "⚠️ 已有任务在运行，请先停止当前任务"
        return
    
    config = {
        'data_type':data_type,
        'files': input_files_text,
        'output_dir': output_path_text.strip(),
        'goal': goal_text.strip(),
        }
    
    model_name = model_choice
    yield from unified_analysis_executor(config, api_key, model_name, execute, "快速模式")

def clear_quick_form():
    """清空快速模式表单"""
    return "MeRIP-seq", "", "", "", "", "",""

# ============================ 通用功能 ==================================
def stop_analysis():
    """停止分析（通用）"""
    if not is_task_running():
        return "⚪ 当前没有运行中的任务"
    
    print("[INFO] Stop button clicked, setting stop flag")
    stop_flag = get_stop_flag()
    stop_flag.set()
    time.sleep(0.5)
    
    return "⏹️ 停止信号已发送\n正在中断:\n• AI调用\n• 代码执行\n• Shell进程\n\n⏳ 请稍候..."

def signal_handler(sig, frame):
    print('\n🛑 Shutting down...')
    stop_flag = get_stop_flag()
    stop_flag.set()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ============================= 界面样式 ========================
# 创建主题
theme = gr.themes.Soft(
    primary_hue="violet",
    secondary_hue="purple",
    neutral_hue="slate",
    font=gr.themes.GoogleFont("Inter"),
    font_mono=gr.themes.GoogleFont("JetBrains Mono"),
    spacing_size="sm",
    radius_size="md"
).set(button_primary_background_fill="linear-gradient(135deg, #667eea 20%, #764ba2 80%)",
    button_primary_background_fill_hover="linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%)",
    button_primary_text_color="white",
    button_primary_border_color="#4c51bf",
    body_text_color="#4a5568",
    background_fill_primary="#f8fafc",
    background_fill_secondary="white",
    border_color_primary="#e2e8f0",
    border_color_accent="#667eea",
    color_accent="#667eea",
    shadow_spread="6px",
    shadow_spread_dark="3px",
    block_shadow="0 10px 30px rgba(0,0,0,0.1)",
    block_border_width="2px",
    block_label_background_fill="linear-gradient(90deg, #667eea20, #764ba220)",
    block_label_text_color="#4a5568",
    block_title_text_color="#2d3748")

# =========================== 创建界面 ==============================
with gr.Blocks(theme=theme, title="AutoM6A 智能分析平台") as demo:
    # 标题
    gr.HTML("""
        <div style="text-align: center; padding: 1rem 0 1.5rem 0;">
            <h1 style="font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; 
                       background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                       -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                 AutoM6A
            </h1>
            <p style="font-size: 1.1rem; color: #64748b; margin: 0;">
                AI-Powered m<sup>6</sup>A Methylation Analysis Platform
            </p>
        </div>
    """)
    
    # 配置区域（全局共享）
    with gr.Accordion("⚙️ Configuration", open=True, elem_classes="config-panel"):
        with gr.Row():
            model_selector = gr.Dropdown(
                label="Model Engine",
                choices=['deepseek-reasoner', 'deepseek-chat', 'gpt-3.5-turbo', 'gpt-4'],
                value='deepseek-reasoner'
            )
        
            api_key_input = gr.Textbox(
                label="API Key",
                placeholder="sk-xxxxxxx",
                scale=2
            )
            
            execute_checkbox = gr.Checkbox(
                label="✓ Execute Code",
                value=True,
                info="Run generated analysis code",
                scale=1
            )
    
    #============================Tab界面=====================================
    with gr.Tabs():
        # ========== Tab 1: 智能对话模式 ==============
        with gr.Tab("💬 Intelligent Chat", id="chat_mode"):
            chat_status_text = gr.Markdown("⚪ Not initialized - Please set API key first", elem_classes="status-badge")
            
            
            chatbot = gr.Chatbot(
                value=[[None, "👋 请先在上方配置区设置API密钥，然后点击【初始化】按钮"]],
                height=500,
                elem_classes="chatbot-container"
            )
                    
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="💭 Enter your analysis needs...",
                    show_label=False,
                    scale=5,
                    elem_classes="input-box"
                )
                    
            send_btn = gr.Button("Send", scale=1.5, variant="primary", elem_classes="primary-btn")
                    
            with gr.Row():
                init_btn = gr.Button("🚀 初始化", variant="secondary", elem_classes="primary-btn")
                reset_btn = gr.Button("🔄 重置", variant="secondary", elem_classes="secondary-btn")
                
            with gr.Accordion("📊 信息状态", open=True):
                slots_display = gr.Textbox(
                    lines=10,
                    interactive=False,
                    show_label=False,
                    elem_classes="info-panel"
                )
                    
            chat_start_btn = gr.Button("▶️ 开始分析", visible=False, elem_classes="primary-btn")
            chat_stop_btn = gr.Button("⏹️ 停止", elem_classes="stop-btn")
            
            with gr.Accordion("📋 执行日志", open=False):
                chat_log_output = gr.TextArea(
                    lines=15,
                    show_label=False,
                    elem_classes="log-output"
                )
            
        # ===================== Tab 2: 快速模式 ======================
        with gr.Tab("⚡ Quick Mode", id="quick_mode"):
            gr.Markdown("""Direct form-based input for experienced users. Fill in the form to quickly start analysis.""")
            
            with gr.Column():
                # 数据类型选择
                with gr.Group(elem_classes="config-section"):
                    gr.Markdown("### 🧬 数据类型选择")
                    data_type_selector = gr.Radio(
                        choices=["MeRIP-seq", "Nanopore"],
                        value="MeRIP-seq",
                        label="请选择要分析的数据类型",
                        info="MeRIP-seq: 二代测序m6A数据 | Nanopore: 三代测序直接RNA测序数据"
                    )
                # Nanopore警告提示框（默认隐藏）
                nanopore_warning = gr.Markdown(visible=False,value="",elem_classes="warning-box")
                # Dorado安装脚本（默认隐藏）
                dorado_install_script = gr.Code(
                    language="shell",
                    label="📜 Dorado参考安装脚本",
                    visible=False,
                    value="",
                    lines=10,
                    max_lines=15
                )
                # 输入区域
                with gr.Group():
                    gr.Markdown("### 📁 数据文件")
                    quick_input_files = gr.TextArea(
                        placeholder="输入文件路径（每行一个），例如:\n"
                                    "/data/sample_R1.fastq.gz: Forward reads\n"
                                    "/data/sample_R2.fastq.gz: Reverse reads\n\n",
                        lines=8,
                        show_label=False
                    )
                
                with gr.Group():
                    gr.Markdown("### 📁 输出路径")
                    quick_output_path = gr.Textbox(
                        placeholder="输入输出目录的绝对路径，例如: /output/analysis_results",
                        lines=1,
                        show_label=False
                    )
                
                with gr.Group():
                    gr.Markdown("### 🎯 分析目标")
                    quick_goal = gr.TextArea(
                        placeholder="详细描述你的分析目标和使用的工具，例如:\n"
                                    "Perform MeRIP-seq data analysis:\n"
                                    "1. Quality control with FastQC\n"
                                    "2. Alignment with HISAT2 to reference genome\n"
                                    "3. Peak calling with MACS2\n"
                                    "💡 提示: 明确指定工具名称可以提高分析准确性",
                        lines=6,
                        show_label=False
                    )
                
                # 按钮区域
                with gr.Row():
                    quick_example_btn = gr.Button("📋 加载示例",variant="secondary")       
                    quick_run_btn = gr.Button("▶️ 运行分析",variant="primary")
                    quick_stop_btn = gr.Button("⏹️ 停止",variant="stop")
                    quick_clear_btn = gr.Button("🔄 清空",variant="secondary")
                
                # 输出区域
                with gr.Accordion("📋 执行日志", open=False):
                    quick_output_log = gr.TextArea(
                        lines=15,
                        show_label=False,
                        elem_classes="log-output"
                    )
    
    # ========================== Tab1 事件绑定 ============================
    # 初始化
    init_btn.click(
        initialize_handler,
        inputs=[api_key_input, model_selector],
        outputs=[chatbot, msg_input, chat_status_text]
    )
    
    # 发送消息
    msg_input.submit(
        chat_message,
        inputs=[msg_input, chatbot, api_key_input, model_selector],
        outputs=[msg_input, chatbot, slots_display, chat_start_btn]
    )
    
    send_btn.click(
        chat_message,
        inputs=[msg_input, chatbot, api_key_input, model_selector],
        outputs=[msg_input, chatbot, slots_display, chat_start_btn]
    )
    
    # 重置对话
    reset_btn.click(
        reset_chat,
        inputs=[api_key_input, model_selector],
        outputs=[chatbot, slots_display, chat_log_output, chat_start_btn, chat_status_text]
    )
    
    # 新对话
    # new_conv_btn.click(
    #     start_new_conversation,
    #     inputs=[api_key_input, model_selector],
    #     outputs=[chatbot, slots_display, chat_log_display, chat_start_btn, chat_status_text]
    # )
    
    # 示例
    # example_btn.click(show_chat_examples, outputs=[chatbot])
    
    # 开始分析
    chat_start_btn.click(start_chat_analysis, inputs=[chatbot, api_key_input, model_selector, execute_checkbox],outputs=[chat_log_output])
    
    # 停止分析
    chat_stop_btn.click(stop_analysis, outputs=[chat_status_text])
    
    # ========================== Tab2 事件绑定 ============================
    # 数据类型改变时的处理
    data_type_selector.change(
        on_data_type_change,
        inputs=[data_type_selector],
        outputs=[nanopore_warning, dorado_install_script, quick_input_files]
    )
    
    # 加载示例
    quick_example_btn.click(load_quick_example, outputs=[quick_input_files, quick_output_path, quick_goal] )
    
    # 运行分析
    quick_run_btn.click(
        quick_start_analysis,
        inputs=[data_type_selector, quick_input_files, quick_output_path, quick_goal, 
                api_key_input, model_selector, execute_checkbox],
        outputs=[quick_output_log]
    )
    
    # 停止分析
    quick_stop_btn.click(stop_analysis, outputs=[quick_output_log])
    
    # 清空表单
    quick_clear_btn.click(
        clear_quick_form,
        outputs=[data_type_selector, nanopore_warning, dorado_install_script, 
                 quick_input_files, quick_output_path, quick_goal, quick_output_log]
    )

# ==================== 启动服务 ====================
if __name__ == "__main__":
    port = 5904
    print("="*50)
    print(f"🚀 AutoM6A 智能分析平台")
    print(f"🔗 http://localhost:{port}")
    print("="*50)
    demo.launch(share=False, server_port=port, server_name='0.0.0.0', show_error=True)