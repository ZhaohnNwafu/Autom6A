#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
智能对话处理器
基于LLM的完全智能化对话管理
"""

from src.information_slots import InformationSlots
from src.llm_extractor import LLMExtractor

class IntelligentChatHandler:
    """智能对话处理器 -支持Nanopore类型数据"""

    def __init__(self, api_key, model_name="deepseek-chat"):
        self.slots = InformationSlots()
        self.extractor = LLMExtractor(api_key, model_name)
        self.conversation_history = []
        self.last_extraction_result = None
        self.is_ready_to_execute = False
        self.dorado_script_shown = False  # 标记是否已显示dorado安装脚本
        print(f"[INFO] IntelligentChatHandler initialized with model: {model_name}")
    
    def get_greeting(self):
        """获取问候语"""
        return """👋 你好！我是 **AutoM6A 智能助手**

我可以通过自然语言对话帮你配置生物信息学数据分析任务。

请**自由地**描述你的分析需求，例如：
• "我想分析拟南芥的m6A数据"（MeRIP-seq二代测序）
• "有一些Nanopore三代测序的m6A数据需要处理"
• "帮我分析Oxford Nanopore直接RNA测序数据"

💡 提示：
- **MeRIP-seq数据**：常规二代测序m6A分析
- **Nanopore数据**：三代测序，需要dorado basecalling
- 明确指定工具名称可以让分析更准确！"""
     
    def generate_dorado_install_script(self):
        """生成dorado安装脚本"""
        return """#!/bin/bash
# Dorado Basecalling Software Installation Script

set -e  # Exit on error
# Configuration
DORADO_VERSION="0.5.3"  # Update to latest version as needed
INSTALL_DIR="${HOME}/software/dorado"
DOWNLOAD_URL="https://cdn.oxfordnanoportal.com/software/analysis/dorado-${DORADO_VERSION}-linux-x64.tar.gz"

# Create installation directory
mkdir -p ${INSTALL_DIR}
cd ${INSTALL_DIR}

# Download dorado
echo "Downloading dorado v${DORADO_VERSION}..."
wget ${DOWNLOAD_URL} -O dorado.tar.gz

# Extract
tar -xvzf dorado.tar.gz

# Make executable
chmod +x bin/dorado

# Verify installation
./bin/dorado --version

# Print path
DORADO_PATH="${INSTALL_DIR}/bin/dorado"
echo "💡 Please provide this path when I ask for data files:"
echo "${DORADO_PATH}: dorado basecaller executable"
echo "========================================="
"""

    def process_message(self, user_input):
        """处理用户消息"""
        if not user_input or not user_input.strip():
            return "请输入你的消息 😊", False
        
        # 特殊命令处理
        if user_input.strip().lower() in ['重新开始', 'restart', 'reset']:
            self.reset()
            return self.get_greeting(), False
        
        # 检查是否是确认执行的命令
        confirm_keywords = ['开始', 'start', 'run', '运行', '确认', 'yes', '好的', 'ok']
        if any(kw in user_input.strip().lower() for kw in confirm_keywords):
            if self.slots.is_complete():
                self.is_ready_to_execute = True
                return "🚀 好的，准备启动分析！请点击右侧的【🚀 开始分析】按钮", True
            else:
                # 拦截并告知用户还差什么
                missing = self.slots.get_missing_required_slots()
                mapping = {"data_type": "数据类型", "files": "数据文件", "output_dir": "输出目录", "goal": "分析目标"}
                missing_names = [mapping.get(m, m) for m in missing]
                self.is_ready_to_execute = False # 确保不会启动
                return f"⚠️ 暂时还不能开始。我还需要您提供：**{', '.join(missing_names)}**。请告诉我这些信息后再试一次。", False
            
        # 使用LLM提取信息
        print(f"[DEBUG] Processing user input: {user_input}")
        try:
            extraction_result = self.extractor.extract(
                user_input,
                self.slots,
                self.conversation_history
            )
        
            print(f"[DEBUG] Extraction result: {extraction_result}")
            
            # 检查提取结果的有效性
            if not extraction_result or 'extracted_info' not in extraction_result:
                print(f"[ERROR] Invalid extraction result")
                extraction_result = {
                    'extracted_info': {},
                    'missing_slots': self.slots.get_missing_required_slots(),
                    'next_question': "抱歉，我没有完全理解。能否重新描述一下？",
                    'confidence': 0.0
                }
            
            # 更新槽位
            if extraction_result['extracted_info']:
                self.slots.update(extraction_result['extracted_info'])
                print(f"[DEBUG] Updated slots: {self.slots.get_filled_slots()}")
                print(f"[DEBUG] Missing slots: {self.slots.get_missing_required_slots()}")
                print(f"[DEBUG] Is complete: {self.slots.is_complete()}")
            
            # 保存提取结果
            self.last_extraction_result = extraction_result
            
            # 生成响应 - 检测Nanopore数据类型
            ai_response = self._generate_response(extraction_result)

            # 检查是否是Nanopore数据且未显示安装脚本
            current_data_type = self.slots.get_filled_slots().get('data_type', '')
            if 'Nanopore' in current_data_type and not self.dorado_script_shown:
                ai_response = self._add_nanopore_warning(ai_response)
                self.dorado_script_shown = True
            # 添加到对话历史    
            self.conversation_history.append([user_input, ai_response])
            
            # 检查是否完成
            is_ready = self.slots.is_complete()
            print(f"[DEBUG] Final is_ready status: {is_ready}")
            
            return ai_response, is_ready
        
        except Exception as e:
            print(f"[ERROR] Exception in process_message: {e}")
            import traceback
            traceback.print_exc()
            
            # 返回友好的错误信息，但不影响后续对话
            error_response = f"抱歉，我遇到了一些技术问题。请重新描述你的需求。\n\n错误详情: {str(e)}"
            self.conversation_history.append([user_input, error_response])
            return error_response, False

    def _add_nanopore_warning(self, base_response):
        """为Nanopore数据添加dorado安装提示"""
        warning = f"""
🔬 **检测到Nanopore三代测序数据！**

⚠️ **重要提醒：**
Nanopore数据分析需要使用 **dorado** 进行basecalling。

**步骤：**
1. **如果已安装dorado**：
   - 记录dorado的绝对路径（如：`/home/user/software/dorado/bin/dorado`）
   - 在提供文件路径时，请包含这个路径

2. **如果未安装dorado**：
   - 我已为您准备了参考安装脚本（见下方）
   - 安装完成后，记录显示的dorado路径

**参考安装脚本：**
```bash
{self.generate_dorado_install_script()}
```

💡 **提示：**
在提供数据文件时，请按以下格式：
```
/path/to/dorado/bin/dorado: dorado basecaller executable
/path/to/fast5_dir/: directory containing fast5 files
/path/to/reference.fa: reference genome
```
"""
        return warning + "\n" + base_response
      
    def _generate_response(self, extraction_result):
        """生成AI响应"""
        # 获取提取的信息
        extracted = extraction_result.get('extracted_info', {})
        next_question = extraction_result.get('next_question', '')
        
        response_parts = []
        
        # 1. 确认提取的信息（如果有新信息）
        if extracted:
            confirmations = []

            # 数据类型 - 特殊标注Nanopore
            if 'data_type' in extracted:
                data_type = extracted['data_type']
                if 'Nanopore' in data_type:
                    confirmations.append(f"数据类型：🔬 {data_type} (三代测序)")
                else:
                    confirmations.append(f"数据类型：{data_type}")
            
            # 物种
            if 'species' in extracted:
                species = extracted['species']
                species_map = {'Arabidopsis': '拟南芥','Rice': '水稻', 'Human': '人类','Mouse': '小鼠'}
                species_cn = species_map.get(species, species)
                confirmations.append(f"物种：{species_cn} ({species})")
            
            # 文件
            if 'files' in extracted:
                files_str = extracted['files']
                # 检查是否包含dorado路径
                if 'dorado' in files_str.lower():
                    confirmations.append(f"数据位置：✓ 包含dorado路径")
                else:
                    confirmations.append(f"数据位置：{files_str}")

            # 输出目录
            if 'output_dir' in extracted:
                confirmations.append(f"输出目录：{extracted['output_dir']}")
            
            # 分析目标
            if 'goal' in extracted:
                goal = extracted['goal']
                goal_display = goal[:150] + "..." if len(goal) > 150 else goal
                confirmations.append(f"分析目标：{goal_display}")
            if confirmations:
                response_parts.append("✓ " + "、".join(confirmations))
        
        # 2. 显示进度
        completeness = self.slots.get_completeness_percentage()
        if completeness < 100:
            response_parts.append(f"\n📊 信息完整度：{completeness}%")
        
        # 3. 检查是否完成
        if self.slots.is_complete():
            response_parts.append(self._generate_config_summary())
        else:
            # 继续收集信息
            if next_question:
               # 如果是Nanopore数据且缺少dorado路径，特别提醒
                current_data_type = self.slots.get_filled_slots().get('data_type', '')
                missing = self.slots.get_missing_required_slots()
                
                if 'Nanopore' in current_data_type and 'files' in missing:
                    next_question += "\n\n⚠️ **Nanopore数据特别提醒**：请确保提供dorado的绝对路径"
                
                response_parts.append(f"\n{next_question}")
        
        return "\n".join(response_parts)
    
    def _generate_config_summary(self):
        """生成配置摘要"""
        filled = self.slots.get_filled_slots()
        
        # 物种显示
        species = filled.get('species', '未指定')
        species_map = {'Arabidopsis': '拟南芥','Rice': '水稻','Human': '人类','Mouse': '小鼠'}
        species_display = f"{species_map.get(species, species)} ({species})"
        
        # goal完整显示
        goal_text = filled.get('goal', '未指定')
        if len(goal_text) > 100:
            goal_lines = [goal_text[i:i+80] for i in range(0, len(goal_text), 80)]
            goal_display = '\n   '.join(goal_lines)
        else:
            goal_display = goal_text
            
        # 数据类型显示 - 特殊标注Nanopore
        data_type = filled.get('data_type', '未指定')
        data_type_display = f"🔬 {data_type} (三代测序)" if 'Nanopore' in data_type else data_type

        summary = f"""
{'='*50}
✅ ***信息收集完成！***
{'='*50}

📋 **分析配置：**

**物种：** {species_display}
**数据类型：** {data_type_display}
**数据位置：** {filled.get('files', '未指定')}
**输出目录：** {filled.get('output_dir', '未指定')}
**分析目标：** {goal_display}
"""
        
        # 添加可选信息
        optional_info = []
        if filled.get('sample_count'):
            optional_info.append(f"样本数量：{filled['sample_count']}")
        if filled.get('sequencing_type'):
            optional_info.append(f"测序类型：{filled['sequencing_type']}")
        if filled.get('threads'):
            optional_info.append(f"线程数：{filled['threads']}")
        
        if optional_info:
            summary += "\n**其他参数：** " + "、".join(optional_info) + "\n"
        
        # Nanopore特殊提示
        if 'Nanopore' in data_type:
            summary += f"""
{'='*50}
🔬 **Nanopore数据分析流程：**
1. fast5 → pod5 格式转换
2. dorado basecalling (包含m6A检测)
3. minimap2 序列比对
4. nanopolish 信号比对
5. m6anet m6A位点检测

{'='*50}
"""
        summary += f"""
{'='*50}

✨ 配置已准备就绪！

• 回复 **"开始"** 或 **"运行"** → 启动分析
• 回复 **"修改"** → 调整配置
• 回复 **"重新开始"** → 清空重来
"""   
        return summary
    
    def get_config_for_agent(self):
        """获取用于启动Agent的配置"""
        if not self.slots.is_complete():
            return None
        
        config = self.slots.to_config()
        
        # 确保files是字符串格式（每行一个文件）
        files_str = config['files']
        if not isinstance(files_str, str):
            files_str = str(files_str)
        
        return {
            'files': files_str,
            'output_dir': config['output_dir'],
            'goal': config['goal'],
            'species': config.get('species'),
            'data_type': config.get('data_type')
        }
    
    def get_slots_display(self):
        """获取槽位信息的显示文本"""
        return self.slots.get_display_info()
    
    def is_ready(self):
        """检查是否准备好执行"""
        return self.slots.is_complete()
    
    def reset(self):
        """重置对话状态"""
        self.slots.reset()
        self.conversation_history = []
        self.last_extraction_result = None
        self.is_ready_to_execute = False
        self.dorado_script_shown = False