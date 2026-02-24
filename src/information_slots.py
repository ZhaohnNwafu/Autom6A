#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
信息槽位管理
管理从用户对话中提取的所有信息
"""
import os
import glob
from typing import List, Union, Optional

class FileManager:
    """文件路径管理器 - 职责单一"""
    
    @staticmethod
    def normalize(value: Union[str, List[str], None]) -> Optional[str]:
        """
        标准化文件路径为统一格式(多行字符串)
        
        Args:
            value: 各种格式的文件输入
            
        Returns:
            标准化后的多行字符串,每行一个文件路径
        """
        if not value:
            return None
        
        # 已经是标准格式
        if isinstance(value, str) and '\n' in value:
            return value.strip()
        
        # 列表格式
        if isinstance(value, list):
            return '\n'.join(str(f).strip() for f in value if f)
        
        # 单个字符串
        if isinstance(value, str):
            value = value.strip()
            
            # 通配符模式
            if '*' in value:
                expanded = FileManager._expand_wildcard(value)
                return '\n'.join(expanded) if expanded else value
            
            # 目录路径
            if os.path.isdir(value):
                return value
            
            # 单个文件
            return value
        
        return str(value)
    
    @staticmethod
    def merge(old_files: Optional[str], new_files: str, action: str = 'auto') -> str:
        """
        合并文件列表 - 简化版
        
        Args:
            old_files: 已有文件(多行字符串)
            new_files: 新文件(多行字符串)
            action: 'add'(增量) | 'replace'(替换) | 'auto'(自动判断)
            
        Returns:
            合并后的文件列表(多行字符串)
        """
        # 解析为列表
        old_list = FileManager._parse_to_list(old_files) if old_files else []
        new_list = FileManager._parse_to_list(new_files)
        
        # 替换模式:直接返回新文件
        if action == 'replace':
            print(f"[FileManager] Replacing files: {len(old_list)} → {len(new_list)}")
            return '\n'.join(new_list)
        
        # 增量模式:合并去重
        if action == 'add' or (action == 'auto' and len(new_list) <= 2 and old_list):
            # 使用字典保持顺序并去重
            merged = {f: None for f in old_list + new_list}
            print(f"[FileManager] Merging files: {len(old_list)} + {len(new_list)} → {len(merged)}")
            return '\n'.join(merged.keys())
        
        # 自动判断为替换
        print(f"[FileManager] Auto-replacing files: {len(old_list)} → {len(new_list)}")
        return '\n'.join(new_list)
    
    @staticmethod
    def validate(files_value: Optional[str]) -> dict:
        """
        验证文件路径
        
        Returns:
            {'valid': bool, 'message': str, 'stats': dict}
        """
        if not files_value:
            return {'valid': False, 'message': '文件路径为空', 'stats': {}}
        
        # 通配符模式 - 跳过验证
        if '*' in files_value:
            return {
                'valid': True,
                'message': f'通配符模式: {files_value[:100]}',
                'stats': {'type': 'wildcard'}
            }
        
        paths = FileManager._parse_to_list(files_value)
        existing = [p for p in paths if os.path.exists(p)]
        
        stats = {
            'total': len(paths),
            'existing': len(existing),
            'missing': len(paths) - len(existing),
            'type': 'paths'
        }
        
        if len(existing) == 0:
            return {
                'valid': False,
                'message': f'所有{len(paths)}个路径都不存在',
                'stats': stats
            }
        
        if len(existing) < len(paths):
            return {
                'valid': True,
                'message': f'{len(existing)}/{len(paths)} 个路径存在',
                'stats': stats
            }
        
        return {
            'valid': True,
            'message': f'所有{len(paths)}个路径都已验证',
            'stats': stats
        }
    
    @staticmethod
    def _parse_to_list(value: str) -> List[str]:
        """解析为路径列表"""
        if not value:
            return []
        return [line.strip() for line in value.split('\n') if line.strip()]
    
    @staticmethod
    def _expand_wildcard(pattern: str) -> Optional[List[str]]:
        """展开通配符"""
        try:
            matches = glob.glob(pattern)
            return sorted(matches) if matches else None
        except Exception as e:
            print(f"[WARN] 无法展开通配符 '{pattern}': {e}")
            return None

class InformationSlots:
    def __init__(self):
        # 必需槽位
        self.required_slots = {       
            'data_type': None,        # 数据类型 (如: MeRIP-seq, RNA-seq)
            'files': None,            # 文件路径或描述
            'output_dir': None,       # 输出目录
            'goal': None              # 分析目标
        }
        
        # 可选槽位
        self.optional_slots = {
            'species': None,          # 物种 (如: Arabidopsis, Rice)
            'sample_count': None,     # 样本数量
            'sequencing_type': None,  # 测序类型 (PE/SE)
            'threads': 8,             # 线程数
            'quality_cutoff': 20,     # 质量阈值
            'reference_genome': None, # 参考基因组路径
            'goal_english': None  # 新增：英文版本的goal
        }
        
        # 槽位描述（用于生成提示）
        self.slot_descriptions = {   
            'data_type': '数据类型（如：MeRIP-seq、RNA-seq）',
            'files': '数据文件路径或位置',
            'output_dir': '分析结果输出目录',
            'goal': '分析目标（如：质量控制、序列比对、peak calling）',
            'species': '研究物种（如：拟南芥/Arabidopsis、水稻/Rice）',
            'sample_count': '样本数量',
            'sequencing_type': '测序类型（双端PE/单端SE）',
            'threads': '使用的线程数',
            'quality_cutoff': '质量过滤阈值',
            'reference_genome': '参考基因组文件路径'
        }

    def update(self, extracted_info):
        """更新槽位信息 - 优化版"""
        for slot_name, value in extracted_info.items():
            if value is None:
                continue
            
            # 类型转换
            if slot_name == 'threads':
                value = self._safe_int(value, default=8)
            elif slot_name == 'quality_cutoff':
                value = self._safe_int(value, default=20)
            
            # 文件字段特殊处理
            if slot_name == 'files':
                action = extracted_info.get('files_action', 'auto')
                old_files = self.required_slots.get('files')
                
                # 标准化新文件
                normalized = FileManager.normalize(value)
                
                # 合并或替换
                self.required_slots['files'] = FileManager.merge(old_files, normalized, action)
                
                # 验证
                validation = FileManager.validate(self.required_slots['files'])
                print(f"[SLOTS] Files update: {validation['message']}")
                
            # 其他路径字段
            elif slot_name in ['output_dir', 'reference_genome']:
                self._validate_path(slot_name, value)
                self._set_slot(slot_name, value)
            
            # 普通字段
            else:
                self._set_slot(slot_name, value)
    def _safe_int(self, value, default):
        """安全的整数转换"""
        try:
            return int(value)
        except:
            return default
    def _set_slot(self, name, value):
        """设置槽位值"""
        if name in self.required_slots:
            self.required_slots[name] = value
        elif name in self.optional_slots:
            self.optional_slots[name] = value

    def _validate_path(self, name, path):
        """私有方法：校验路径是否存在"""
        if isinstance(path, str) and os.path.exists(path):
            print(f"[INFO] Path verified for {name}: {path}")
        else:
            print(f"[WARN] Path not found or invalid for {name}: {path}")
    
    def get_all_slots(self):
        """获取所有槽位信息"""
        return {**self.required_slots, **self.optional_slots}
    
    def get_filled_slots(self):
        """获取已填充的槽位"""
        filled = {}
        all_slots = self.get_all_slots()
        for name, value in all_slots.items():
            if value is not None:
                filled[name] = value
        return filled
    
    def get_missing_required_slots(self):
        """获取缺失的必需槽位"""
        missing = []
        for name, value in self.required_slots.items():
            if value is None:
                missing.append(name)
        return missing
    
    def is_complete(self):
        """检查必需槽位是否全部填充"""
        return len(self.get_missing_required_slots()) == 0
    
    def get_completeness_percentage(self):
        """获取完整度百分比"""
        total = len(self.required_slots)
        filled = total - len(self.get_missing_required_slots())
        return int((filled / total) * 100)
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'required': self.required_slots.copy(),
            'optional': self.optional_slots.copy()
        }
    
    def to_config(self):
        """转换为Agent可用的配置格式"""
        config = {
            'files': self._format_files_for_agent(),
            'output_dir': self.required_slots['output_dir'],
            'goal': self.required_slots['goal'],
            'species': self.optional_slots['species'],
            'data_type': self.required_slots['data_type']
        }
        
        # 添加可选参数
        if self.optional_slots.get('threads'):
            config['threads'] = self.optional_slots['threads']
        if self.optional_slots.get('quality_cutoff'):
            config['quality_cutoff'] = self.optional_slots['quality_cutoff']
        
        return config
    
    def _format_files_for_agent(self):
        """
        格式化文件列表供Agent使用
        输出格式: 每行一个文件路径的字符串
        """
        files = self.required_slots.get('files')
        if not files:
            return ""
        
        # 已经是多行格式
        if isinstance(files, str) and '\n' in files:
            return files
        
        # 单个路径
        if isinstance(files, str):
            files_str = files.strip()
            
            # 如果是目录,尝试展开
            if os.path.isdir(files_str):
                bio_files = self._list_bio_files(files_str)
                if bio_files:
                    return '\n'.join(bio_files)
                return files_str
            
            # 如果包含通配符,尝试展开
            if '*' in files_str:
                expanded = FileManager._expand_wildcard(files_str)
                if expanded:
                    return '\n'.join(expanded)
                return files_str
            
            # 单个文件
            return files_str
        
        # 列表格式
        if isinstance(files, list):
            return '\n'.join(str(f) for f in files if f)
        
        return str(files)
    
    def _list_bio_files(self, directory):
        """列出目录下的生信文件"""
        bio_exts = ('.fastq', '.fq', '.bam', '.sam', '.fasta', '.fa', 
                   '.fastq.gz', '.fq.gz', '.bed', '.vcf','.gtf','.gff')
        try:
            all_files = os.listdir(directory)
            bio_files = [os.path.join(directory, f) for f in all_files 
                        if any(f.endswith(ext) for ext in bio_exts)]
            return sorted(bio_files)
        except Exception as e:
            print(f"[WARN] Cannot list files in {directory}: {e}")
            return []
       
    def get_display_info(self):
        """
        获取用于界面显示的信息
        Returns:
            格式化的显示字符串
        """
        lines = []
        lines.append(f"📊 信息完整度: {self.get_completeness_percentage()}%")
        lines.append("")
        
        # 必需信息
        lines.append("【必需信息】")
        for name, value in self.required_slots.items():
            desc = self.slot_descriptions[name]
            if value is not None:
                # 文件信息特殊显示
                if name == 'files':
                    display_value = self._format_files_display(value)
                    lines.append(f"✓ {desc}:")
                    lines.append(f"  {display_value}")
                # goal字段特殊处理 - 可能较长
                elif name == 'goal':
                    # 如果goal超过100字符，显示前100字+省略号
                    if len(str(value)) > 100:
                        display_value = str(value)[:100] + "..."
                        lines.append(f"✓ {desc}:")
                        lines.append(f"  {display_value}")
                    else:
                        lines.append(f"✓ {desc}: {value}")
                else:
                    lines.append(f"✓ {desc}: {value}")
            else:
                lines.append(f"⚠ {desc}: 待补充")
        
        # 可选信息（只显示已填充的）
        filled_optional = {k: v for k, v in self.optional_slots.items() 
                          if v is not None and k in self.slot_descriptions}
        if filled_optional:
            lines.append("")
            lines.append("【可选信息】")
            for name, value in filled_optional.items():
                desc = self.slot_descriptions[name]
                lines.append(f"✓ {desc}: {value}")
        
        return '\n'.join(lines)
    
    def _format_files_display(self, files_value):
        """格式化文件信息用于显示"""
        if not files_value:
            return "未指定"
        
        # 多行格式
        if '\n' in files_value:
            file_list = [f.strip() for f in files_value.split('\n') if f.strip()]
            count = len(file_list)
            if count <= 3:
                return '\n  '.join(file_list)
            else:
                preview = '\n  '.join(file_list[:2])
                return f"{preview}\n  ... 共{count}个文件"
        
        # 通配符
        if '*' in files_value:
            return f"{files_value} (通配符模式)"
        
        # 目录
        if isinstance(files_value, str) and os.path.isdir(files_value):
            bio_files = self._list_bio_files(files_value)
            if bio_files:
                return f"{files_value} (含{len(bio_files)}个生信文件)"
            return f"{files_value} (目录)"
        
        # 单个文件
        return files_value
    
    def reset(self):
        """重置所有槽位"""
        self.__init__()
