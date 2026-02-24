from copy import deepcopy
from src.build_RAG_private import retrive
import time

class PromptGenerator:
    def __init__(self, blacklist='', engine = None, rag = True, retriever = None,data_type='MeRIP-seq'):
        self.history_summary = ''
        self.current_goal = None
        self.global_goal = None
        self.tasks = None
        self.engine = engine
        self.rag = rag
        self.retriever = retriever
        self.data_type = data_type  # 保存数据类型
        self.blacklist = blacklist.split(',')
        self.speciallist = ['sra-toolkit: mamba install sra-tools',
                            'trim_galore: mamba install trim-galore',
                            'macs2: pip install macs2']
        # 记录已检索的内容，避免重复检索
        self.rag_cache = {}

        self.system_expert_prompt = (
            "You are a universal bioinformatics expert AI. You are proficient in various omics "
            "(m6A, RNA-seq, ATAC-seq, Single Cell, etc.) and familiar with the tool chain in Linux environment. "
            "Your task is to design the optimal analysis plan based on the file list and goals provided by the user."
            "\nCore principles:\n"
            "1. Rigor: File format must be checked before processing, and quality control (QC) included in the steps.\n"
            "2. Path management: All outputs must go to the specified output_dir with clear naming rules for intermediate files.\n"
            "3. Modular: Generated scripts should be executed step by step with simple comments."
        )
        self.system_prompt_prefix = """
        🌍 LANGUAGE REQUIREMENT (CRITICAL):
        You MUST respond ONLY in English, regardless of the user's input language.
        This is a HARD requirement to optimize token usage and maintain consistency.
        """
        
    def get_executor_prompt(self, executor_info):
        prompt = {
            "task": "I executed a Bash script and obtained log output detailing its execution. Kindly assist me in assessing the success of the script. If it encounters any failures, please aid in summarizing the reasons for the failure and propose modifications to the code.",
            "rules": [
                "You should only respond in JSON format with fixed format.",
                "Your JSON response should only be enclosed in double quotes.",
                "No such file or directory is error."
                "You should not write anything outside {}.",
                "You should make your answer as detailed as possible.",
            ],
            "log output": [executor_info],
            "fixed format": {
                "stat": "0 or 1, 0 indicates failure and 1 indicates success",
                "info": "summarize errors in one sentence."
            }
        }
        final_prompt = prompt
        return final_prompt

    def get_prompt(self, data_list, goal_description, global_round, execute_success=True, execute_info=None, last_execute_code=None):
        """
        生成提示词,根据数据类型动态调整RAG检索策略
        """
        self.current_goal = goal_description

        # ============ 阶段1：规划阶段 (global_round == 0) ============
        if global_round == 0:
            self.global_goal = goal_description
            # 为Nanopore数据添加特殊的规划指导
            if self.data_type == "Nanopore":
                # 获取Nanopore工作流知识
                if self.rag:
                    nanopore_workflow = retrive(
                        self.retriever,
                        retriever_prompt="Nanopore direct RNA sequencing m6A complete workflow pod5 dorado nanopolish m6anet",
                        top_k=5,
                        verbose=True
                    )
                else:
                    nanopore_workflow = ""
                
                prompt = {
                    "role": f"Act as a Nanopore sequencing bioinformatician specialist. The rules must be STRICTLY followed!",
                    "rules": [
                        f"When acting as a bioinformatician, you strictly cannot stop acting as a bioinformatician.",
                        f"All rules must be followed strictly.",
                        f"⚠️ CRITICAL: This is a Nanopore direct RNA sequencing m6A modification detection project.",
                        f"⚠️ MANDATORY: You MUST use the following tools in order: pod5, dorado, minimap2, samtools, nanopolish, m6anet.",
                        f"⚠️ DO NOT use Tombo, modkit, or other alternative tools.",
                        f"Your plan MUST include these exact steps:",
                        f"  1. Convert fast5 to pod5 format (using pod5 tool)",
                        f"  2. Basecalling with m6A detection (using dorado)",
                        f"  3. Read alignment to transcriptome (using minimap2)",
                        f"  4. Signal-to-reference alignment (using nanopolish eventalign)",
                        f"  5. m6A modification detection (using m6anet)",
                        f"You should only respond in JSON format with my fixed format.",
                        f"Your JSON response should only be enclosed in double quotes and you can have only one JSON in your response.",
                        f"You should not write loading data as a separate step.",
                        f"You should not write anything else except for your JSON response.",
                        f"You should make your plan detailed and specify which tool to use in each step."
                    ],
                    "input": [
                        f"You have the following information in a list with the format file path: file description. I provide those files to you, so you don't need to prepare the data.",
                        data_list
                    ],
                    "goal": self.current_goal,
                    "MANDATORY Workflow Reference (MUST FOLLOW)": nanopore_workflow if nanopore_workflow else "Standard Nanopore m6A workflow: pod5 convert → dorado basecaller → minimap2 alignment → nanopolish eventalign → m6anet detection",
                    f"fixed format for JSON response": {
                        "plan": [
                            f"Your detailed step-by-step sub-tasks in a list to finish your goal. Each step MUST specify the tool name to use, for example: ['step 1: Convert fast5 to pod5 using pod5 tool', 'step 2: Basecalling with dorado', 'step 3: Alignment using minimap2', etc.].\n"
                        ]
                    }
                }
            else:
                # 标准MeRIP-seq规划
                prompt = {
                    "role": f"Act as a bioinformatician, the rules must be strictly followed!",
                    "rules": [
                        f"When acting as a bioinformatician, you strictly cannot stop acting as a bioinformatician.",
                        f"All rules must be followed strictly.",
                        f"You should use information in input to write a detailed plan to finish your goal.",
                        f"You should include the software name and should not use those software: {self.blacklist}.",
                        f"You should only respond in JSON format with my fixed format.",
                        f"Your JSON response should only be enclosed in double quotes and you can have only one JSON in your response.",
                        f"You should not write loading data as a separate step.",
                        f"You should not write anything else except for your JSON response.",
                        f"You should make your answer as detailed as possible."
                    ],
                    "input": [
                        f"You have the following information in a list with the format file path: file description. I provide those files to you, so you don't need to prepare the data.",
                        data_list
                    ],
                    "goal": self.current_goal,
                    f"fixed format for JSON response": {
                        "plan": [
                            f"Your detailed step-by-step sub-tasks in a list to finish your goal, for example: ['step 1: content', 'step 2: content', 'step 3: content'].\n"
                        ]
                    }
                }
            
            final_prompt = prompt
        # ============ 阶段2：代码生成阶段 (global_round > 0) ============
        else:
            # Code generation阶段 - 根据数据类型使用不同的RAG策略
            if self.rag:
                if self.data_type == "Nanopore":
                    # Nanopore数据：优先检索专门的流程文档
                    retriever_info = retrive(
                        self.retriever,
                        retriever_prompt=f"Nanopore direct RNA sequencing m6A modification workflow complete pipeline fast5 pod5 dorado nanopolish m6anet",
                        top_k=5,  # 获取更多相关文档
                        verbose=True
                    )
                    
                    # 如果检索到的内容较少，尝试更通用的查询
                    if len(retriever_info) < 500:
                        print(f"[RAG WARNING] First retrieval returned only {len(retriever_info)} chars, trying alternative query...")
                        retriever_info = retrive(
                            self.retriever,
                            retriever_prompt=f"nanopore m6a pod5 dorado nanopolish m6anet pipeline",
                            top_k=5,
                            verbose=True
                        )
                    # 验证是否包含关键工具
                    required_tools = ['pod5', 'dorado', 'nanopolish', 'm6anet']
                    missing_tools = [tool for tool in required_tools if tool.lower() not in retriever_info.lower()]
                    
                    if missing_tools:
                        print(f"[RAG WARNING] Missing tools in retrieval: {missing_tools}")
                        print(f"[RAG INFO] Retrieved {len(retriever_info)} characters")
                        print(f"[RAG PREVIEW] {retriever_info[:500]}...")
                else:
                    # MeRIP-seq数据：使用通用检索
                    retriever_info = retrive(
                        self.retriever,
                        retriever_prompt=f'{self.current_goal}',
                        top_k=1,
                        verbose=False
                    )
            else:
                retriever_info = ''
           
            # 根据数据类型添加特定的代码要求
            code_requirements = [
                f"You should not use those software: {self.blacklist}.",
                "You don't need to create and activate the mamba environment abc_runtime.",
                'You should always add conda-forge and bioconda to the list of channels.',
                'You should always install dependencies and software you need to use with mamba or pip with -y.',
                'You should pay attention to the number of input files and do not miss any.',
                'You should process each file independently and can not use FOR loop.',
                'You should use the path for all files according to input and history.',
                'You should use the default values for all parameters that are not specified.',
                'You should not repeat what you have done in history.',
                'You should only use software directly you installed with mamba or pip.',
                'If you use Rscript -e, you should make sure all variables exist in your command, otherwise, you need to check your history to repeat previous steps and generate those variables.',
                "You should not write anything else except for your JSON response.",
                # "If RAG is provided, you should use it as template to write codes. You should not copy the RAG directly.",
            ]
            
            # Nanopore特定要求
            if self.data_type == "Nanopore":
                code_requirements.extend([
                    "⚠️ CRITICAL: You MUST strictly follow the workflow described in the RAG knowledge base below.",
                    "⚠️ MANDATORY: Use ONLY the tools specified in the RAG workflow: pod5, dorado, minimap2, samtools, nanopolish, m6anet.",
                    " - Simply install required software directly with 'mamba install' or 'pip install'",
                    " - For m6anet (final step only): You can create a separate environment ONLY if absolutely necessary",
                    "For Nanopore data analysis, you MUST use dorado for basecalling with modified base calling enabled.",
                    "The dorado executable path is provided in the input file list - use it directly.",
                    "For m6A detection from Nanopore data, the pipeline MUST include: pod5 conversion -> dorado basecalling -> alignment -> nanopolish eventalign -> m6anet dataprep -> m6anet inference.",
                    "You MUST create two conda environments: 'nanopore_abc' (Python 3.9) and 'm6anet_abc' (Python 3.8).",
                    "Follow the EXACT command templates from the RAG knowledge base and adapt to actual file paths.",
                    "Installation pattern: First check if tool exists, if not: 'mamba install -c bioconda -c conda-forge <tool> -y' or 'pip install <tool>'"
                ])
            else:
                code_requirements.append("If RAG is provided, you should use it as a REFERENCE TEMPLATE to write codes. You should NOT copy the RAG directly but adapt it to the current task.")
            prompt = {
                "role": "Act as a bioinformatician, the rules must be strictly followed!",
                "rules": [
                    "When acting as a bioinformatician, you strictly cannot stop acting as a bioinformatician.",
                    "All rules must be followed strictly.",
                    "You are provided a system with specified constraints.",
                    "The history of what you have done is provided, you should take the name changes of some files into account, or use some output from previous steps.",
                    "You should use all information you have to write bash codes to finish your current task.",
                    "All code requirements must be followed strictly when you write codes.",
                    "You should only respond in JSON format with my fixed format.",
                    "Your JSON response should only be enclosed in double quotes.",
                    "You should make your answer as simple as possible.",
                    "You should not write anything else except for your JSON response.",
                    'You should use full absolute path for all files.',
                    "If you need to use 'macs2' software, please install it using 'pip install'."
                ],
                "system": [
                    "You have a Ubuntu 20.04 system",
                    "You have a mamba environment named abc_runtime",
                    "You do not have any other software installed"
                ],
                "input": [
                        "You have the following information in a list with the format file path: file description. I provide those files to you, so you don't need to prepare the data.",
                        data_list
                    ],
                "history": self.history_summary,
                "current task": self.current_goal,
                "code requirement": code_requirements,
                "RAG Knowledge Base (IMPORTANT - Use as reference template)": retriever_info if retriever_info else "No specific workflow knowledge available, use standard bioinformatics practices.",
                "fixed format for JSON response": {
                    "tool": "name of the tool you use",
                    "code": "bash code to finish the current task."
                }
            }

            if execute_success:
                final_prompt = prompt
            else:
                final_prompt = prompt
                final_prompt['history'] += f' You previously generated codes: {last_execute_code}. However, your code has errors and you should fix them: {execute_info}.'

        return final_prompt

    def set_tasks(self, tasks):
        self.tasks = deepcopy(tasks)

    def slow_print(self, input_string, speed=0.01):
        for char in str(input_string):
            # 使用print函数打印每个字符，并设置end参数为空字符串，以避免在每个字符之间输出换行符
            try:
                print(char, end='', flush=True)
            except:
                print(char, end='')
            time.sleep(speed)
        print()

    def format_user_prompt(self, prompt, global_round, gui_mode):
        INFO_STR = ''
        if gui_mode:
            print(f'[Round {global_round}]')
            print(f'[USER]')
            INFO_STR += f'[Round {global_round}] \n\n'
            for key in prompt:
                self.slow_print(f"{key}", speed=0.001)
                self.slow_print(prompt[key], speed=0.001)
                INFO_STR += f"{key} \n\n {prompt[key]} \n\n"
        else:
            print(f'\033[31m[Round {global_round}]\033[0m')
            print(f'\033[32m[USER]\033[0m')
            INFO_STR += f'\033[31m[Round {global_round}]\033[0m \n\n'
            for key in prompt:
                self.slow_print(f"\033[34m{key}\033[0m", speed=0.001)
                self.slow_print(prompt[key], speed=0.001)
                INFO_STR += f"\033[34m{key}\033[0m \n\n {prompt[key]} \n\n"
        print()
        return INFO_STR

    def format_ai_response(self, response_message, gui_mode):
        INFO_STR = ''
        if gui_mode:
            print(f'[AI]')
            for key in response_message:
                self.slow_print(f"{key}", speed=0.01)
                self.slow_print(response_message[key], speed=0.01)
                INFO_STR += f"{key} \n\n {response_message[key]} \n\n"
            print(f'-------------------------------------')
        else:
            print(f'\033[32m[AI]\033[0m')
            for key in response_message:
                self.slow_print(f"\033[34m{key}\033[0m", speed=0.01)
                self.slow_print(response_message[key], speed=0.01)
                INFO_STR += f"\033[34m{key}\033[0m \n\n {response_message[key]} \n\n"
            print(f'\033[33m-------------------------------------\033[0m')
        print()
        return INFO_STR

    def add_history(self, task, global_round, data_list, code = None):
        if global_round == 0:
            self.history_summary += f"Firstly, you have input with the format 'file path: file description' in a list: {data_list}. You wrote a detailed plan to finish your goal. Your global goal is {self.global_goal}. Your plan is {self.tasks}. \n"
        else:
            self.history_summary += f"Then, you finished the task: {task} with code: {code}.\n"