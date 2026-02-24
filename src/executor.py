import subprocess
import time,os,sys
import signal
import threading

class CodeExecutor:
    def __init__(self):
        self.bash_code_path = None
        # 🔧 修改1: 优化前缀命令，移除重复的activate
        self.code_prefix = [
            'eval "$(mamba shell hook --shell bash)"',
            'mamba activate abc_runtime',
        ]
        self.code_postfix = []
        # 新增：进程管理
        self.current_process = None
        self.process_lock = threading.Lock()
        self.is_interrupted = False

    def execute(self, bash_code_path, stop_flag=None):
        """
        执行bash脚本，支持中断
        
        Args:
            bash_code_path: bash脚本路径
            stop_flag: 停止标志 (threading.Event，可选)
            
        Returns:
            str: 执行信息（stdout + stderr）
        """
        self.bash_code_path = bash_code_path
        self.is_interrupted = False

        # 读取原始bash的内容
        with open(self.bash_code_path, 'r') as input_file:
            bash_content = input_file.read()

        self.bash_code_path_execute = self.bash_code_path + '.execute.sh'

        # 🔧 修改2: 清理脚本内容，移除重复的activate命令
        cleaned_content = self._clean_script_content(bash_content)

        # 生成带prefix和postfix的执行脚本
        with open(self.bash_code_path_execute, 'w') as output_file:
            for code in self.code_prefix:
                output_file.write(code + '\n')
            # 写入原始内容
            output_file.write(cleaned_content)
            output_file.write('\n')  # 确保在新行开始
            for code in self.code_postfix:
                output_file.write(code + '\n')

        # 启动监控线程（如果提供了stop_flag）
        if stop_flag:
            monitor_thread = threading.Thread(
                target=self._monitor_stop_flag,
                args=(stop_flag,),
                daemon=True
            )
            monitor_thread.start()   

        try:
            # 启动子进程 # 🔧 修改3: 移除 -i 标志，使用非交互式bash
            with self.process_lock:
                # Linux/Mac平台：创建新进程组
                self.current_process = subprocess.Popen(
                    ['bash', '-e', self.bash_code_path_execute],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid,
                    env=self._prepare_env()  # 🔧 修改4: 准备环境变量
                )
            
            print(f"[EXECUTOR] Process started: PID={self.current_process.pid}")

            # 实时读取输出
            stdout = []
            while True:
                # 检查是否被中断
                if self.is_interrupted:
                    print("[EXECUTOR] Execution interrupted by user")
                    break
                
                output = self.current_process.stdout.readline()
                if output == '' and self.current_process.poll() is not None:
                    break
                if output:
                    print(f'[stdout] {output.strip()}')
                    stdout.append(f'[stdout] {output.strip()}')

            # 读取stderr
            stderr = []
            if self.current_process.stderr:
                for line in self.current_process.stderr.readlines():
                     # 🔧 修改5: 过滤掉conda/mamba的警告信息
                    if any(x in line for x in ['EnvironmentNameNotFound', 
                                                'terminal process group',
                                                'no job control',
                                                'shell.bash hook']):
                        continue
                    if '\n' == line:
                        continue
                    print(f"[stderr] {line}", end='')
                    stderr.append(line)

            # 保留最后10行
            if len(stdout) > 10:
                stdout = stdout[-10:]
            if len(stderr) > 10:
                stderr = stderr[-10:]

            stdout_str = '\n'.join(stdout)
            stderr_str = '\n'.join(stderr)

            # 等待进程结束
            if not self.is_interrupted:
                self.current_process.communicate()
                return_code = self.current_process.returncode
                print(f"[EXECUTOR] Process finished: return_code={return_code}")
            
            with self.process_lock:
                self.current_process = None

            # 如果被中断，返回中断信息
            if self.is_interrupted:
                return "Process interrupted by user\n" + stdout_str + '\n' + stderr_str

            executor_info = stdout_str + '\n' + stderr_str
            return executor_info

        except Exception as e:
            print(f"[EXECUTOR] Exception during execution: {e}")
            with self.process_lock:
                self.current_process = None
            return f"Execution error: {str(e)}"

    def _clean_script_content(self, content):
        """
        🔧 新增方法: 清理脚本内容
        - 移除重复的 mamba activate abc_runtime
        - 确保每个环境只激活一次
        """
        lines = content.split('\n')
        cleaned_lines = []
        seen_activations = set()
        
        for line in lines:
            stripped = line.strip()
            
            # 跳过重复的 abc_runtime 激活
            if 'mamba activate abc_runtime' in stripped:
                if 'abc_runtime' not in seen_activations:
                    seen_activations.add('abc_runtime')
                    cleaned_lines.append(line)
                continue
            
            # 跳过重复的 conda hook
            if 'conda shell.bash hook' in stripped:
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def _prepare_env(self):
        """
        🔧 新增方法: 准备环境变量
        确保conda/mamba能正常工作
        """
        env = os.environ.copy()
        
        # 确保conda路径在PATH中
        conda_paths = [
            '/home/malab21/.conda',
            '/home/malab21/mambaforge',
            '/opt/conda',
            os.path.expanduser('~/mambaforge'),
            os.path.expanduser('~/miniconda3'),
        ]
        
        for conda_path in conda_paths:
            if os.path.exists(conda_path):
                bin_path = os.path.join(conda_path, 'bin')
                if bin_path not in env.get('PATH', ''):
                    env['PATH'] = f"{bin_path}:{env.get('PATH', '')}"
                break
        
        # 禁用conda的自动激活警告
        env['CONDA_AUTO_ACTIVATE_BASE'] = 'false'
        
        return env
      
    def _monitor_stop_flag(self, stop_flag):
        """监控停止标志的线程"""
        print("[EXECUTOR] Stop monitor thread started")
        while True:
            if stop_flag.is_set():
                print("[EXECUTOR] Stop flag detected, terminating process...")
                self.terminate()
                break
            time.sleep(0.3)  # 每300ms检查一次

    def terminate(self):
        """终止当前运行的进程"""
        with self.process_lock:
            if self.current_process and self.current_process.poll() is None:
                try:
                    pid = self.current_process.pid
                    print(f"[EXECUTOR] Terminating process {pid}...")
                    self.is_interrupted = True
                    
                    # Unix/Linux: 杀死整个进程组
                    try:
                        pgid = os.getpgid(pid)
                        print(f"[EXECUTOR] Killing process group {pgid}...")
                            
                        # 先发送SIGTERM（优雅终止）
                        os.killpg(pgid, signal.SIGTERM)
                            
                        # 等待2秒
                        try:
                            self.current_process.wait(timeout=2)
                            print(f"[EXECUTOR] Process group {pgid} terminated")
                        except subprocess.TimeoutExpired:
                            # 如果还没结束，强制杀死
                            print(f"[EXECUTOR] Force killing process group {pgid}...")
                            os.killpg(pgid, signal.SIGKILL)
                            self.current_process.wait()
                            print(f"[EXECUTOR] Process group {pgid} killed")
                    except ProcessLookupError:
                        # 进程已经结束
                        print(f"[EXECUTOR] Process {pid} already terminated")
                    except Exception as e:
                        print(f"[EXECUTOR] Error during killpg: {e}")
                        # 备用方案：直接kill进程
                        try:
                            self.current_process.terminate()
                            self.current_process.wait(timeout=2)
                        except:
                            self.current_process.kill()
                            self.current_process.wait()
                    
                except Exception as e:
                    print(f"[EXECUTOR] Error terminating process: {e}")
                finally:
                    self.current_process = None
            else:
                print("[EXECUTOR] No active process to terminate")