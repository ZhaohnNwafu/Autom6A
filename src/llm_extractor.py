#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
优化版LLM信息提取器
更智能、更快、更稳定
"""

import json
import re,os
from openai import OpenAI

class LLMExtractor:
    """智能的信息提取器"""
    def __init__(self, api_key, model_name="deepseek-chat"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/"
        )
        # 预编译的系统提示(只需加载一次)
        self.system_prompt = self._load_system_prompt()
        print(f"[INFO] Using model: {model_name}")
    
    def _load_system_prompt(self) -> str:
        """加载系统提示 - 新增三代测序知识"""
        return """你是生信AI助手,从对话中提取分析所需信息。

核心槽位(4个必需):
1. data_type - 数据类型(MeRIP-seq/RNA-seq/Nanopore-m6A...)
2. files - 文件路径(支持目录/列表/通配符)
3. output_dir - 输出目录
4. goal - 分析目标(保留用户原文)

📝 **路径解析规则（极其重要）**:
当用户说"数据路径为A，B，C"或"文件是A, B, C"时：
- 识别所有路径，按换行符分隔
- dorado路径：包含"dorado"字符串的路径
- fast5目录：包含"fast5"的目录路径
- 参考基因组：.fa, .fasta结尾的文件
- **必须全部提取**，不能只提取最后一个！

示例输入："数据路径为/tools/dorado/bin/dorado，/data/fast5_dir，/ref/genome.fa"
正确输出：
```json
{
  "files": "/tools/dorado/bin/dorado: dorado basecaller executable\\n/data/fast5_dir: directory containing fast5 files\\n/ref/genome.fa: reference genome"
}
```

🔄 **修改意图识别（关键）**:
修改关键词：["修改"，"改成"，"改为"，"换成"，"应该是"，"不对"，"重新"，"更正"，"更新"]

- 如果用户说"修改XX为YY" → files_action: "replace"
- 如果用户说"输出目录改成/new/path" → 直接替换output_dir，files_action: "replace"
- 如果用户说"添加/增加" → files_action: "add"
- **默认情况**：新提供的完整路径列表 → files_action: "replace"

示例：
```
已有files: "/old/path"
用户: "改成/new/path" → {"files":"/new/path", "files_action":"replace"}
用户: "还有/add/path" → {"files":"/add/path", "files_action":"add"}
```
🆕 三代测序专用识别:
- 关键词: 三代/纳米孔/Nanopore/ONT/Oxford/fast5/MinION/PromethION
- 数据类型自动映射为: Nanopore-m6A / Nanopore-RNA / Nanopore
- 文件格式: fast5 (原始信号) 或 fastq (basecalled)

可选槽位:
5. species (Arabidopsis/Rice/Human/Mouse)
6. sample_count, threads...
7. files_action (add/replace/auto)

关键规则:
• goal必须完整保留用户原话,不做任何简化或翻译
• 智能推断: "m6A"→MeRIP-seq, "拟南芥"→Arabidopsis, "三代m6A"→Nanopore-m6A, "fast5文件"→Nanopore
• **路径必须全部提取，用换行符分隔**
• **准确识别修改vs增加意图**
• 返回JSON: {"extracted_info": {...}, "missing_slots": [...], "next_question": "..."}"""

    def extract(self, user_input, current_slots, conversation_history=None):
        """从用户输入中提取信息 - 超级智能版本"""
        # 1. 快速正则预提取(1ms内完成)
        direct_result = self._smart_fallback_extract(user_input, current_slots)
        
        # 2. 如果正则提取到关键信息,且置信度高,直接返回
        if self._is_high_confidence_extraction(direct_result):
            print(f"[INFO] Using fast regex extraction (confident)")
            return direct_result
        
        # 3. 否则调用LLM(带缓存)
        try:
            prompt = self._build_super_prompt(user_input, current_slots, conversation_history)
            response = self._call_llm(prompt)
            result = self._parse_response(response, current_slots)
            
            # 4. 合并LLM和正则的结果(取最优)
            return self._merge_results(result, direct_result)
            
        except Exception as e:
            print(f"[ERROR] LLM extraction failed: {e}")
            # 降级到正则结果
            return direct_result
    
    def _build_super_prompt(self, user_input, current_slots, history):
        """构建超级智能提示词"""   
        # 当前状态(紧凑格式)
        filled = current_slots.get_filled_slots()
        missing = current_slots.get_missing_required_slots()
        
        # 特别标注已有files
        files_hint = ""
        if 'files' in filled:
            file_lines = filled['files'].split('\n')
            count = len(file_lines)
            files_hint = f"\n⚠️ 已有{count}个文件/路径:\n"
            for i, line in enumerate(file_lines[:3], 1):
                files_hint += f"  {i}. {line[:60]}...\n" if len(line) > 60 else f"  {i}. {line}\n"
            if count > 3:
                files_hint += f"  ... 共{count}项"

        state_str = f"""📊 当前: {json.dumps(filled, ensure_ascii=False) if filled else '空'}{files_hint}
❓ 缺失: {', '.join(missing) if missing else '完整'} ({current_slots.get_completeness_percentage()}%)"""
        
        # 精简历史(只保留最近2轮摘要)
        history_str = ""
        if history and len(history) > 0:
            recent = history[-2:]
            history_str = "\n💬 历史:\n" + "\n".join([
                f"用户: {msg[0][:60]}..." if len(msg[0]) > 60 else f"用户: {msg[0]}"
                for msg in recent if isinstance(msg, list) and len(msg) >= 1
            ])
        
        # 核心示例(只保留最关键的3个)
        examples = """关键示例:
1️⃣ **多路径解析**（最重要）:
输入: "数据路径为/tools/dorado/bin/dorado，/data/fast5，/ref/genome.fa"
输出: {"files":"/tools/dorado/bin/dorado: dorado basecaller\\n/data/fast5: fast5 directory\\n/ref/genome.fa: reference genome"}

2️⃣ **修改vs增加**:
已有files: "/old/path"
输入: "改成/new/path" → {"files":"/new/path","files_action":"replace"}
输入: "还有/add/path" → {"files":"/add/path","files_action":"add"}

3️⃣ **完整路径列表**（Nanopore）:
输入: "路径为A，B，C"（3个路径）
输出: {"files":"A\\nB\\nC","files_action":"replace"}"""
        
        # 用户提示
        user_prompt = f"""{state_str}
{history_str}

{examples}

🎯 当前输入: "{user_input}"

**任务**:
1. 提取所有路径（逗号分隔的多个路径必须全部提取）
2. 判断是修改(replace)还是增加(add)
3. goal保留原文
4. 返回JSON

注意：如果用户提供多个路径（如"A，B，C"），必须全部提取并用\\n分隔！"""
        
        return self.system_prompt, user_prompt

    def _is_high_confidence_extraction(self, result) -> bool:
        """判断正则提取是否高置信度"""
        extracted = result.get('extracted_info', {})
        # 如果提取到3个以上关键字段,认为是高置信度
        key_fields = {'data_type', 'files', 'output_dir', 'goal', 'species'}
        extracted_keys = set(extracted.keys()) & key_fields
        return len(extracted_keys) >= 3
    
    def _merge_results(self, llm_result, regex_result):
        """合并LLM和正则的提取结果,取最优"""
        merged_info = {}
        
        # LLM优先(通常更准确)
        merged_info.update(llm_result.get('extracted_info', {}))
        
        # 正则补充LLM遗漏的
        for key, value in regex_result.get('extracted_info', {}).items():
            if key not in merged_info or not merged_info[key]:
                merged_info[key] = value
        
        return {
            'extracted_info': merged_info,
            'missing_slots': llm_result.get('missing_slots', []),
            'next_question': llm_result.get('next_question', ''),
            'confidence': max(llm_result.get('confidence', 0), regex_result.get('confidence', 0))
        }
    
    def _call_llm(self, prompt):
        """调用DeepSeek API - 优化版"""
        system_prompt, user_prompt = prompt
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                print(f"[DEBUG] Calling LLM API (attempt {retry_count + 1}/{max_retries})...")
                
                # 不使用 response_format，因为可能导致空响应
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=1000
                )
                
                content = response.choices[0].message.content
                
                # 检查响应是否为空
                if not content or not content.strip():
                    print(f"[WARN] Empty response from LLM")
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        continue
                    else:
                        raise Exception("LLM返回空响应")
                
                print(f"[DEBUG] LLM API call successful, response length: {len(content)}")
                return content
                
            except Exception as e:
                retry_count += 1
                print(f"[ERROR] API call failed (attempt {retry_count}/{max_retries}): {error_msg}")
                
                if retry_count < max_retries:
                    import time
                    time.sleep(retry_count*2)
                else:
                    raise Exception(f"API调用失败: {e}")
    
    def _parse_response(self, response_text, current_slots):
        """解析LLM响应 - 增强容错"""
        print(f"[DEBUG] Raw LLM response (first 500 chars): {response_text[:500]}")
        
        try:
            # 清理可能的markdown标记
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # 解析JSON
            result = json.loads(cleaned)
            
            # 验证和修复
            if 'extracted_info' not in result:
                result['extracted_info'] = {}

            # 重要：确保extracted_info中的值不是None
            if result['extracted_info']:
                result['extracted_info'] = {k: v for k, v in result['extracted_info'].items() if v is not None}  
            
            if 'missing_slots' not in result:
                # 自动计算缺失槽位
                updated_slots = current_slots.get_all_slots().copy()
                if result['extracted_info']:
                    updated_slots.update(result['extracted_info'])
                missing = [k for k, v in updated_slots.items() 
                          if v is None and k in current_slots.required_slots]
                result['missing_slots'] = missing
            
            if 'next_question' not in result or not result['next_question']:
                # 生成默认问题
                missing = result.get('missing_slots', [])
                if missing:
                    result['next_question'] = f"还需要：{', '.join(missing)}"
                else:
                    result['next_question'] = "信息已完整！"
            
            result.setdefault('confidence', 0.8)
            result.setdefault('reasoning', '')
            
            # 打印调试信息
            print(f"[DEBUG] Extracted: {result['extracted_info']}")
            print(f"[DEBUG] Missing: {result['missing_slots']}")
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse failed: {e}")
            return self._smart_fallback_extract(response_text, current_slots)
    
    def _smart_fallback_extract(self, text, current_slots):
        """备用提取方案 - 增强三代数据识别"""
        print("[INFO] Using fallback extraction")
        
        # 确保text是字符串
        if not isinstance(text, str):
            text = str(text)

        extracted = {}
        text_lower = text.lower()

        # ============ 🆕 优先检测三代测序数据 ============
        nanopore_keywords = [
            'nanopore', '纳米孔', '三代', 'ont', 'oxford',
            'minion', 'promethion', 'fast5', 'gridion'
        ]
        
        is_nanopore = any(kw in text_lower for kw in nanopore_keywords)
        
        if is_nanopore:
            extracted['data_type'] = 'Nanopore-m6A'
            extracted['sequencing_platform'] = 'Nanopore'
            print(f"[FALLBACK] ✓ Detected Nanopore sequencing data")

        # ============ 提取文件路径 ============
        files_info = self._extract_files_smartly(text, text_lower)
        if files_info:
            extracted.update(files_info)
 
        # ============ 提取分析目标  ============
        # 尝试识别包含目标描述的部分
        goal_patterns = [
            r'(?:分析目标|目标|goal|analysis|要做|需要|想要)[：:]\s*(.+?)(?:\n|$)',
            r'(?:用|使用|with|using)\s+\w+\s*(?:做|进行|来|for)',  # 匹配含工具名的描述
        ]
        
        goal_text = None
        for pattern in goal_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                goal_text = match.group(1) if match.lastindex else match.group(0)
                break
        
        # 如果没有明确的目标标记，检查是否整段都是描述目标
        if not goal_text and any(kw in text_lower for kw in ['质控', 'qc', '比对', 'align', 'peak', '分析', 'analysis', 'basecalling','m6anet','nanopolish']):
            # 提取包含分析相关关键词的内容
            sentences = [s.strip() for s in text.split('，') if s.strip()]
            goal_sentences = [s for s in sentences if any(kw in s.lower() for kw in 
                ['质控', 'qc', 'fastqc', '比对', 'align', 'hisat', 'peak', 'macs', '分析','basecalling','dorado','m6anet','nanopolish'])]
            if goal_sentences:
                goal_text = ', '.join(goal_sentences)
        
        if goal_text:
            extracted['goal'] = goal_text.strip()
            print(f"[FALLBACK] Extracted goal (original): {extracted['goal'][:100]}...")
        
        # ================ 提取物种===================
        species_patterns = {
            'Arabidopsis': [r'拟南芥', r'arabidopsis', r'\bath\b', r'tair'],
            'Rice': [r'水稻', r'rice', r'oryza'],
            'Human': [r'人类?', r'human', r'homo\s+sapiens'],
            'Mouse': [r'小鼠', r'mouse', r'mus\s+musculus']
        }
        for species, patterns in species_patterns.items():
            for pattern in patterns:
                try:
                    if re.search(pattern, text_lower):
                        extracted['species'] = species
                        print(f"[FALLBACK] Extracted species: {species}")
                        break
                except Exception as e:
                    print(f"[WARN] Regex error for pattern {pattern}: {e}")
            if 'species' in extracted:
                break
        
        # ============ 提取数据类型 ============
        if 'data_type' not in extracted:
            datatype_patterns = {
                'MeRIP-seq': [r'm6a', r'merip', r'甲基化', r'm6A'],
                'RNA-seq': [r'rna[-\s]?seq', r'转录组', r'rna测序'],
                'ChIP-seq': [r'chip[-\s]?seq', r'芯片测序']
            }
            for dtype, patterns in datatype_patterns.items():
                for pattern in patterns:
                    try:
                        if re.search(pattern, text_lower):
                            extracted['data_type'] = dtype
                            print(f"[FALLBACK] Extracted data_type: {dtype}")
                            break
                    except: pass         
                if 'data_type' in extracted:
                    break
            
        # ============ 计算缺失槽位 ============
        all_slots = current_slots.required_slots.copy()
        all_slots.update(extracted)
        missing = [k for k, v in all_slots.items() if v is None]
        
        # 生成更友好的问题
        if missing:
            missing_cn = {
                'species': '物种','data_type': '数据类型',
                'files': '文件路径','output_dir': '输出目录',
                'goal': '分析目标'
            }
            missing_names = [missing_cn.get(m, m) for m in missing]
            # 🆕 三代数据特殊提示
            if is_nanopore and 'files' in missing:
                next_question = f"我理解了这是Nanopore三代测序数据。还需要：{', '.join(missing_names)}。\n⚠️ 请提供dorado路径、fast5目录和参考基因组/转录组"
            else:
                next_question = f"我理解了部分信息。还需要：{', '.join(missing_names)}"
        else:
            next_question = "信息已完整！"
        
        result = {
            'extracted_info': extracted,
            'missing_slots': missing,
            'next_question': next_question,
            'confidence':0.85 if is_nanopore else 0.7,
            'reasoning': '检测到Nanopore数据' if is_nanopore else '使用智能规则提取'
        }
        
        print(f"[FALLBACK] Final extracted: {extracted}")
        return result
    
    def _extract_files_smartly(self, text, text_lower):
        """智能提取文件信息 - 增强fast5识别"""
        result = {}
        paths = []
        print(f"\n[FILES] Starting smart extraction...")
        
        # ============ 策略1: 优先处理逗号分隔的多路径 ============
        multi_path_patterns = [
            r'(?:路径|文件|数据)(?:为|是|：|:)\s*(.+?)(?:\n|$|。)',
            r'(?:有|包括|包含)(?:文件|数据)?\s*[:：]?\s*(.+?)(?:\n|$|。)',
        ]
        
        multi_paths_found = False
        for pattern in multi_path_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                path_str = match.group(1).strip()
                print(f"[FILES] Step 1: Matched path string: {path_str[:100]}")
                
                # 按标点分割
                raw_paths = re.split(r'[,，、;；]', path_str)
                print(f"[FILES] Step 2: Split into {len(raw_paths)} parts")
                
                for i, p in enumerate(raw_paths, 1):
                    p = p.strip()
                    # 检查是否是有效路径
                    if (p.startswith('/') or re.match(r'[A-Z]:\\', p)) and len(p) > 3:
                        paths.append(p)
                        print(f"[FILES]   Part {i}: ✓ Valid path: {p[:60]}")
                        multi_paths_found = True
                    else:
                        print(f"[FILES]   Part {i}: ✗ Not a path: {p[:60]}")
                
                if multi_paths_found:
                    break
        
        # ============ 策略2: 备用单路径提取 ============
        if not multi_paths_found:
            print("[FILES] Step 1: No multi-path pattern, using single extraction")
            try:
                unix_paths = re.findall(r'/[^\s，,;；。!！?？\n]+', text)
                paths.extend(unix_paths)
                print(f"[FILES] Step 2: Found {len(unix_paths)} Unix paths")
            except Exception as e:
                print(f"[WARN] Unix path extraction error: {e}")
            
            try:
                win_paths = re.findall(r'[A-Z]:\\[^\s，,;；。!！?？\n]+', text)
                paths.extend(win_paths)
            except: pass
        
        print(f"[FILES] Total found: {len(paths)} paths")

        # ============ 策略3: 智能分类路径 ============
        bio_exts = ['.fastq', '.fq', '.fastq.gz', '.fq.gz', '.bam', '.sam', 
                    '.fasta', '.fa', '.fast5', 'pod5', '.bed', '.vcf', '.gtf', '.gff']
        
        final_files = []
        dorado_path = None
        fast5_dir = None
        reference_genome = None
        output_dir = None
        
        print(f"[FILES] Step 3: Classifying paths...")
        
        for path in paths:
            try:
                path = path.rstrip('。，,;；!！?？、')
                if not path or len(path) < 2:
                    continue
                
                path_lower = path.lower()
                
                # 优先识别dorado
                if 'dorado' in path_lower and 'bin' in path_lower:
                    dorado_path = path
                    print(f"[FILES]   ✓ Dorado executable: {path}")
                    continue
                
                # 识别fast5目录
                if 'fast5' in path_lower and not path.endswith('.fast5'):
                    fast5_dir = path
                    print(f"[FILES]   ✓ Fast5 directory: {path}")
                    continue
                
                # 识别参考基因组
                if path.endswith(('.fa', '.fasta', '.fa.gz', '.fasta.gz')):
                    reference_genome = path
                    print(f"[FILES]   ✓ Reference genome: {path}")
                    continue
                
                # 生信文件
                is_bio_file = any(path_lower.endswith(ext) for ext in bio_exts)
                if is_bio_file:
                    final_files.append(path)
                    print(f"[FILES]   ✓ Bio file: {os.path.basename(path)}")
                    continue
                
                # 上下文分析
                path_idx = text.find(path)
                if path_idx >= 0:
                    context_start = max(0, path_idx - 30)
                    context_end = min(len(text), path_idx + len(path) + 30)
                    context = text[context_start:context_end].lower()
                    
                    output_keywords = ['输出', 'output', '结果', '保存']
                    input_keywords = ['数据', 'data', '文件', 'file', '目录']
                    
                    if any(kw in context for kw in output_keywords):
                        output_dir = path
                        print(f"[FILES]   ✓ Output dir: {path}")
                    elif any(kw in context for kw in input_keywords):
                        final_files.append(path)
                        print(f"[FILES]   ✓ Input dir: {path}")
                
            except Exception as e:
                print(f"[WARN] Error processing path '{path}': {e}")

        # ============ 策略4: 组装files字段（Nanopore优先） ============
        assembled_files = []
        
        if dorado_path:
            assembled_files.append(f"{dorado_path}: dorado basecaller executable")
        
        if fast5_dir:
            assembled_files.append(f"{fast5_dir}: directory containing fast5 files")
        
        if reference_genome:
            assembled_files.append(f"{reference_genome}: reference genome")
        
        # 添加其他文件
        for f in final_files:
            if f not in [dorado_path, fast5_dir, reference_genome]:
                assembled_files.append(f)
        
        if assembled_files:
            result['files'] = '\n'.join(assembled_files)
            print(f"[FILES] ✅ Assembled {len(assembled_files)} files:")
            for i, f in enumerate(assembled_files, 1):
                print(f"[FILES]   {i}. {f[:80]}")
        
        if output_dir:
            result['output_dir'] = output_dir
            print(f"[FILES] ✅ Output directory: {output_dir}")
        
        # ============ 策略5: 检测修改意图 ============
        modify_keywords = ['修改', '改成', '改为', '换成', '应该是', '不对', '重新', '更正']
        add_keywords = ['添加', '增加', '还有', '以及', '另外']
        
        has_modify = any(kw in text for kw in modify_keywords)
        has_add = any(kw in text for kw in add_keywords)
        
        if has_modify:
            result['files_action'] = 'replace'
            print(f"[FILES] 🔄 Intent: REPLACE (modification keywords)")
        elif has_add:
            result['files_action'] = 'add'
            print(f"[FILES] ➕ Intent: ADD (addition keywords)")
        else:
            if len(assembled_files) >= 2:
                result['files_action'] = 'replace'
                print(f"[FILES] 🔄 Intent: REPLACE (multiple paths)")
            else:
                result['files_action'] = 'auto'
                print(f"[FILES] 🤖 Intent: AUTO")
        
        print(f"[FILES] Extraction complete\n")
        
        return result if result else None