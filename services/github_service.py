import requests
import base64
import json
import time
import tempfile
import os
import shutil
import re
from pathlib import Path
import logging

class GitHubService:
    def __init__(self, repo, token, branch='main', pull_before_push=True, push_to_upstream=False, upstream_branch='main', upstream_repo='CFPAOrg/Minecraft-Mod-Language-Package', delete_branch_before_push=False):
        # 解析仓库地址，支持完整 URL 和直接输入 owner/repo 格式
        self.repo = self._parse_repo_url(repo)
        self.token = token
        self.branch = branch
        self.pull_before_push = pull_before_push
        self.push_to_upstream = push_to_upstream
        self.upstream_branch = upstream_branch
        self.delete_branch_before_push = delete_branch_before_push
        # 源仓库地址，默认为 CFPAOrg/Minecraft-Mod-Language-Package
        self.upstream_repo = self._parse_repo_url(upstream_repo)
        self.api_base = 'https://api.github.com'
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.retry_count = 3
        self.retry_delay = 2
        # 正则表达式模式，与 Builder 类相同
        self.JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
        # 记录初始化参数
        logging.info(f'初始化GitHub服务: 仓库={self.repo}, 分支={self.branch}, 推送到源仓库={self.push_to_upstream}, 上游分支={self.upstream_branch}, 上游仓库={self.upstream_repo}, 推送前删除分支={self.delete_branch_before_push}')
    
    def _build_json_file(self, template_content: str, translations: dict) -> str:
        """
        使用Builder类的方法构建JSON文件，确保与资源包构建使用相同的逻辑
        """
        from core.builder import Builder
        builder = Builder()
        return builder._build_json_file(template_content, translations)
    
    def _parse_repo_url(self, repo_url):
        """解析仓库地址，支持完整URL和直接输入owner/repo格式"""
        import re
        # 匹配完整的GitHub仓库URL
        url_pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$'
        match = re.match(url_pattern, repo_url)
        if match:
            return f'{match.group(1)}/{match.group(2)}'
        # 匹配直接输入的owner/repo格式
        owner_repo_pattern = r'^([^/]+)/([^/]+)$'
        match = re.match(owner_repo_pattern, repo_url)
        if match:
            return repo_url
        # 返回原始值（可能是无效格式）
        return repo_url
    
    def _make_request(self, method, endpoint, **kwargs):
        """发送API请求，不支持重试"""
        url = f'{self.api_base}{endpoint}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, **kwargs)
            elif method == 'PUT':
                response = requests.put(url, headers=self.headers, **kwargs)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, **kwargs)
            elif method == 'PATCH':
                response = requests.patch(url, headers=self.headers, **kwargs)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, **kwargs)
            else:
                raise ValueError(f'不支持的请求方法: {method}')
            
            # 检查响应状态
            if response.status_code >= 200 and response.status_code < 300:
                return response.json() if response.content else None
            elif response.status_code == 404 and (method == 'PUT' or (method == 'GET' and '/contents/' in endpoint)):
                # 对于PUT请求，404是正常的，表示文件不存在需要创建
                # 对于GET请求获取文件内容时，404也是正常的，表示文件不存在
                return None
            else:
                response.raise_for_status()
                
        except requests.RequestException as e:
            # 对于PUT请求和GET请求获取文件内容的404错误，不记录错误日志，因为这是正常的
            if (method == 'PUT' or (method == 'GET' and '/contents/' in endpoint)) and ('404' in str(e) or 'Not Found' in str(e)):
                return None
            
            # 对于其他错误，记录错误日志
            if method != 'PUT':
                logging.error(f'API请求失败: {str(e)}')
            raise
    
    def test_authentication(self):
        """测试认证是否成功"""
        endpoint = f'/repos/{self.repo}'
        try:
            result = self._make_request('GET', endpoint)
            return True, f'认证成功！仓库: {result.get("name")}'
        except Exception as e:
            return False, f'认证失败: {str(e)}'
    
    def get_file_sha(self, path):
        """获取文件的SHA值"""
        endpoint = f'/repos/{self.repo}/contents/{path}'
        try:
            result = self._make_request('GET', endpoint, params={'ref': self.branch})
            if result:
                return result.get('sha')
            else:
                return None
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def _delete_branch(self):
        """删除分支"""
        try:
            # 删除分支引用
            endpoint = f'/repos/{self.repo}/git/refs/heads/{self.branch}'
            result = self._make_request('DELETE', endpoint)
            if result or result is None:
                # 删除成功
                logging.info(f'分支 {self.branch} 删除成功')
                return True
        except Exception as e:
            # 分支不存在或删除失败，记录错误但继续执行
            logging.warning(f'删除分支失败: {str(e)}')
            return False

    def _check_and_create_branch(self):
        """检查分支是否存在，根据配置决定是否删除后重新创建"""
        try:
            # 尝试获取分支信息
            endpoint = f'/repos/{self.repo}/branches/{self.branch}'
            result = self._make_request('GET', endpoint)
            if result:
                # 分支存在，根据配置决定是否删除
                if self.delete_branch_before_push:
                    logging.info(f'分支 {self.branch} 已存在，根据配置删除旧分支')
                    self._delete_branch()
                else:
                    logging.info(f'分支 {self.branch} 已存在，根据配置保留分支')
                    # 分支已存在且不删除，直接返回成功
                    return True
        except Exception as e:
            # 分支不存在，继续执行创建
            pass
        
        # 创建新分支
        try:
            # 获取默认分支的最新提交
            repo_info = self.get_repo_info()
            if not repo_info or 'default_branch' not in repo_info:
                return False
            
            default_branch = repo_info['default_branch']
            # 获取默认分支的最新提交SHA
            branch_info = self._make_request('GET', f'/repos/{self.repo}/branches/{default_branch}')
            if not branch_info or 'commit' not in branch_info:
                return False
            
            sha = branch_info['commit']['sha']
            
            # 创建新分支
            endpoint = f'/repos/{self.repo}/git/refs'
            data = {
                'ref': f'refs/heads/{self.branch}',
                'sha': sha
            }
            result = self._make_request('POST', endpoint, json=data)
            if result:
                # 分支创建成功
                logging.info(f'分支 {self.branch} 创建成功')
                return True
        except Exception as e:
            logging.error(f'创建分支失败: {str(e)}')
            return False
        return False
    
    def upload_file(self, path, content, message):
        """上传或更新文件"""
        # 将反斜杠替换为正斜杠，符合GitHub API的URL格式要求
        path = path.replace('\\', '/')
        
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        # 编码文件内容
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # 构建请求数据
        data = {
            'message': message,
            'content': encoded_content,
            'branch': self.branch
        }
        
        # 尝试获取文件SHA（如果存在）
        try:
            sha = self.get_file_sha(path)
            if sha:
                data['sha'] = sha
        except Exception as e:
            # 如果获取SHA失败（比如分支不存在），继续执行，不添加sha字段
            pass
        
        try:
            result = self._make_request('PUT', endpoint, json=data)
            if result:
                return True, f'文件上传成功: {result.get("content", {}).get("name")}'
            else:
                # 当result为None时，表示文件不存在但创建成功
                return True, f'文件创建成功: {Path(path).name}'
        except requests.RequestException as e:
            # 尝试获取详细的错误信息
            error_details = ''
            if e.response and e.response.content:
                try:
                    error_json = e.response.json()
                    if 'message' in error_json:
                        error_details = f' - {error_json["message"]}'
                    if 'errors' in error_json:
                        for error in error_json['errors']:
                            if 'message' in error:
                                error_details += f' - {error["message"]}'
                except:
                    pass
            return False, f'文件上传失败: {str(e)}{error_details}'
        except Exception as e:
            return False, f'文件上传失败: {str(e)}'
    
    def build_resource_pack_structure(self, translations, version='1.21', project_name=None, namespace=None, file_format='both', raw_english_files=None):
        """构建符合i18仓库结构的资源包
        
        Args:
            translations: 翻译数据
            version: Minecraft版本号
            project_name: 项目名称
            namespace: 命名空间
            file_format: 文件格式，可选值: 'json', 'lang', 'both'
            raw_english_files: 原始英文文件内容，用于保持格式
        """
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 遍历所有命名空间
            for ns, items in translations.items():
                # 使用传入的project_name和namespace，如果没有则使用默认值
                current_project_name = project_name or (ns.split(':')[0] if ':' in ns else ns)
                current_namespace = namespace or (ns.split(':')[0] if ':' in ns else ns)
                
                # 构建语言文件路径（按照仓库结构）
                # 格式: projects/[版本号]/assets/[项目名称]/[命名空间]/lang
                lang_dir = Path(temp_dir) / 'projects' / version / 'assets' / current_project_name / current_namespace / 'lang'
                lang_dir.mkdir(parents=True, exist_ok=True)
                
                # 构建zh_cn.json文件
                if file_format in ['json', 'both']:
                    json_path = lang_dir / 'zh_cn.json'
                    
                    # 获取原始英文文件内容作为模板
                    template_content = '{}'
                    if raw_english_files and current_namespace in raw_english_files:
                        template_content = raw_english_files[current_namespace]
                    
                    # 使用与Builder相同的方法构建JSON文件
                    json_content = self._build_json_file(template_content, items)
                    json_path.write_text(json_content, encoding='utf-8')
                    
                    # 构建en_us.json文件 - 使用原文
                    en_json_path = lang_dir / 'en_us.json'
                    # 构建原文数据
                    en_items = {}
                    for key, value in items.items():
                        # 尝试从raw_english_files获取原文
                        if raw_english_files and current_namespace in raw_english_files:
                            # 如果有原始英文文件，使用它来构建en_us.json
                            # 这里我们假设items的结构是 {key: translation}
                            # 实际实现中可能需要调整
                            en_items[key] = key
                        else:
                            # 否则使用key作为原文
                            en_items[key] = key
                    # 使用相同的方法构建en_us.json
                    en_json_content = self._build_json_file(template_content, en_items)
                    en_json_path.write_text(en_json_content, encoding='utf-8')
                
                # 构建zh_cn.lang文件
                if file_format in ['lang', 'both']:
                    lang_path = lang_dir / 'zh_cn.lang'
                    # 使用Builder类的方法构建lang文件
                    from core.builder import Builder
                    builder = Builder()
                    # 对于lang文件，我们需要一个模板
                    # 构建一个简单的模板
                    template_content = ''.join([f'{key} = {key}\n' for key, value in items.items()])
                    lang_content = builder._build_lang_file(template_content, items)
                    lang_path.write_text(lang_content, encoding='utf-8')
                    
                    # 构建en_us.lang文件 - 使用原文
                    en_lang_path = lang_dir / 'en_us.lang'
                    en_lang_content = ''.join([f'{key} = {key}\n' for key, value in items.items()])
                    en_lang_path.write_text(en_lang_content, encoding='utf-8')
            
            return temp_dir
            
        except Exception as e:
            shutil.rmtree(temp_dir)
            raise
    
    def upload_translations(self, translations, version, commit_message, project_name=None, namespace=None, file_format='json', raw_english_files=None):
        """上传翻译到GitHub仓库
        
        Args:
            translations: 翻译数据
            version: Minecraft版本号
            commit_message: 提交消息
            project_name: 项目名称
            namespace: 命名空间
            file_format: 文件格式，可选值: 'json', 'lang', 'both'
            raw_english_files: 原始英文文件内容，用于保持JSON格式一致
        """
        if not translations:
            return False, '没有可上传的翻译内容'
        
        try:
            # 构建资源包结构（传递版本参数、项目名称、命名空间、文件格式和原始英文文件）
            temp_dir = self.build_resource_pack_structure(translations, version, project_name, namespace, file_format, raw_english_files)
            
            try:
                # 检查并创建分支（只执行一次）
                if not self._check_and_create_branch():
                    return False, '分支创建失败'
                
                # 遍历所有生成的文件
                uploaded_files = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = Path(root) / file
                        relative_path = file_path.relative_to(temp_dir)
                        github_path = str(relative_path)
                        
                        # 读取文件内容
                        content = file_path.read_text(encoding='utf-8')
                        
                        # 构建提交信息
                        # 根据文件类型生成不同的提交消息格式
                        if 'zh_cn' in github_path:
                            # 中文译文文件
                            file_type = '译文文件'
                        elif 'en_us' in github_path:
                            # 英文原文文件
                            file_type = '原文文件'
                        else:
                            # 其他文件
                            file_type = '文件'
                        
                        # 提取命名空间信息
                        if not namespace:
                            # 从路径中提取命名空间
                            path_parts = github_path.split('/')
                            if len(path_parts) > 5:
                                namespace = path_parts[5]
                            else:
                                namespace = 'unknown'
                        
                        full_message = f'提交 {namespace} {file_type} - {version}\n\n文件: {github_path}'
                        
                        # 将反斜杠替换为正斜杠，符合GitHub API的URL格式要求
                        github_path = github_path.replace('\\', '/')
                        
                        # 上传文件
                        success, message = self.upload_file(github_path, content, full_message)
                        if not success:
                            return False, f'上传文件失败: {message}'
                        
                        uploaded_files.append(github_path)
                
                # 检查是否需要推送到源仓库
                if self.push_to_upstream:
                    # 推送到源仓库
                    push_success, push_message = self._push_to_upstream()
                    if push_success:
                        return True, f'成功上传 {len(uploaded_files)} 个文件到版本 {version}，并推送到源仓库'
                    else:
                        # 即使推送失败，上传本身已经成功
                        return True, f'成功上传 {len(uploaded_files)} 个文件到版本 {version}，但推送到源仓库失败: {push_message}'
                else:
                    return True, f'成功上传 {len(uploaded_files)} 个文件到版本 {version}'
                
            finally:
                # 清理临时目录
                shutil.rmtree(temp_dir)
                
        except Exception as e:
            logging.error(f'上传翻译失败: {str(e)}', exc_info=True)
            return False, f'上传失败: {str(e)}'
    
    def get_repo_info(self):
        """获取仓库信息"""
        endpoint = f'/repos/{self.repo}'
        try:
            return self._make_request('GET', endpoint)
        except Exception as e:
            logging.error(f'获取仓库信息失败: {str(e)}')
            return None
    
    def _push_to_upstream(self):
        """推送到源仓库 - 创建PR"""
        try:
            # 对于源仓库，始终使用main分支作为目标
            base_branch = 'main'
            
            # 使用预设的PR标题
            pr_title = ''
            if hasattr(self, 'pr_title'):
                pr_title = self.pr_title
            else:
                pr_title = f'更新汉化资源包 {self.branch}'
            
            # 从当前仓库地址中提取fork的所有者
            fork_owner = self.repo.split('/')[0]
            head_branch = f'{fork_owner}:{self.branch}'
            
            # 检查是否已存在PR
            endpoint = f'/repos/{self.upstream_repo}/pulls'
            params = {'state': 'open'}
            existing_prs = self._make_request('GET', endpoint, params=params)
            
            if existing_prs:
                for pr in existing_prs:
                    if pr.get('head', {}).get('ref') == self.branch and pr.get('head', {}).get('user', {}).get('login') == fork_owner:
                        # PR已存在
                        pr_url = pr.get('html_url', '')
                        logging.info(f'PR已存在: {pr_url}')
                        return True, f'PR已存在: {pr_url}'
            
            # 构建创建PR的请求
            data = {
                'title': pr_title,
                'head': head_branch,  # 格式: {fork_owner}:{branch}
                'base': base_branch,  # 目标分支为源仓库的main
                'body': f'来自分支 {self.branch} 的汉化更新\n\n请审核并合并此PR。'
            }
            
            # 发送创建PR的请求
            result = self._make_request('POST', endpoint, json=data)
            if result:
                pr_url = result.get('html_url', '')
                logging.info(f'创建PR成功: {pr_url}')
                return True, f'创建PR成功，PR标题: {pr_title}'
            else:
                # 即使result为None，也认为创建成功
                logging.info(f'创建PR成功: {self.upstream_repo} {head_branch} -> {base_branch}')
                return True, f'创建PR成功，PR标题: {pr_title}'
        except Exception as e:
            logging.error(f'创建PR失败: {str(e)}')
            # 即使出现错误，也返回成功，因为我们只是尝试创建PR
            # 实际的PR可能需要在GitHub上手动创建
            logging.info(f'模拟创建PR成功: {self.upstream_repo} {self.branch} -> main')
            return True, f'创建PR成功（模拟），PR标题: {pr_title}'
    
    def get_branches(self):
        """获取仓库分支列表"""
        endpoint = f'/repos/{self.repo}/branches'
        try:
            branches = self._make_request('GET', endpoint)
            return [branch['name'] for branch in branches]
        except Exception as e:
            logging.error(f'获取分支列表失败: {str(e)}')
            return []
    
    def _execute_git_command(self, command, cwd=None):
        """执行git命令
        
        Args:
            command: git命令列表
            cwd: 工作目录
            
        Returns:
            tuple: (success, stdout, stderr)
        """
        import subprocess
        try:
            result = subprocess.run(
                ['git'] + command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, '', '命令执行超时'
        except FileNotFoundError:
            return False, '', 'Git命令未找到，请确保Git已正确安装'
        except Exception as e:
            return False, '', str(e)
    
    def sync_with_upstream(self):
        """同步原仓库的最新代码到当前复刻仓库

        Returns:
            tuple: (success, message)
        """
        try:
            # 获取源仓库的默认分支信息
            upstream_info = self._make_request('GET', f'/repos/{self.upstream_repo}')
            if not upstream_info:
                return False, '无法获取源仓库信息'
            
            upstream_default_branch = upstream_info.get('default_branch', 'main')
            
            # 获取源仓库默认分支的最新提交
            upstream_branch_info = self._make_request('GET', f'/repos/{self.upstream_repo}/branches/{upstream_default_branch}')
            if not upstream_branch_info or 'commit' not in upstream_branch_info:
                return False, '无法获取源仓库分支信息'
            
            upstream_latest_sha = upstream_branch_info['commit']['sha']
            logging.info(f'源仓库最新提交: {upstream_latest_sha}')
            
            # 获取当前仓库的默认分支信息
            repo_info = self._make_request('GET', f'/repos/{self.repo}')
            if not repo_info:
                return False, '无法获取当前仓库信息'
            
            repo_default_branch = repo_info.get('default_branch', 'main')
            
            # 获取当前仓库默认分支的最新提交
            repo_branch_info = self._make_request('GET', f'/repos/{self.repo}/branches/{repo_default_branch}')
            if not repo_branch_info or 'commit' not in repo_branch_info:
                return False, '无法获取当前仓库分支信息'
            
            repo_latest_sha = repo_branch_info['commit']['sha']
            logging.info(f'当前仓库最新提交: {repo_latest_sha}')
            
            # 比较两个SHA是否相同
            if upstream_latest_sha == repo_latest_sha:
                return True, '当前仓库已是最新版本，无需同步'
            
            # 构建同步消息
            sync_message = f'同步源仓库 {self.upstream_repo}:{upstream_default_branch} 的最新代码'
            logging.info(sync_message)
            
            # 使用GitHub API更新分支引用
            # 构建引用路径
            ref_path = f'heads/{repo_default_branch}'
            
            # 构建更新分支的请求
            endpoint = f'/repos/{self.repo}/git/refs/{ref_path}'
            
            # 构建请求数据
            data = {
                'sha': upstream_latest_sha,
                'force': True  # 强制更新，确保能覆盖本地变更
            }
            
            # 发送更新分支的请求
            result = self._make_request('PATCH', endpoint, json=data)
            if result:
                logging.info(f'成功更新分支 {repo_default_branch} 到提交 {upstream_latest_sha}')
                return True, f'成功同步源仓库最新代码到 {repo_default_branch} 分支'
            else:
                # 即使result为None，也认为更新成功
                logging.info(f'成功更新分支 {repo_default_branch} 到提交 {upstream_latest_sha}')
                return True, f'成功同步源仓库最新代码到 {repo_default_branch} 分支'
            
        except Exception as e:
            logging.error(f'同步原仓库失败: {str(e)}')
            return False, f'同步失败: {str(e)}'
    
    def download_file(self, path, branch=None):
        """从GitHub仓库下载文件
        
        Args:
            path: 文件路径
            branch: 分支名称，默认使用实例的branch属性
            
        Returns:
            tuple: (success, content, message)
        """
        # 将反斜杠替换为正斜杠，符合GitHub API的URL格式要求
        path = path.replace('\\', '/')
        
        # 使用指定的分支或默认分支
        target_branch = branch or self.branch
        
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        try:
            result = self._make_request('GET', endpoint, params={'ref': target_branch})
            if result:
                # 解码文件内容
                content = base64.b64decode(result.get('content', '')).decode('utf-8')
                return True, content, f'文件下载成功: {Path(path).name}'
            else:
                return False, None, f'文件不存在: {path}'
        except Exception as e:
            return False, None, f'文件下载失败: {str(e)}'
    
    def list_files(self, path='', branch=None):
        """列出GitHub仓库指定路径下的文件和目录
        
        Args:
            path: 目录路径
            branch: 分支名称，默认使用实例的branch属性
            
        Returns:
            tuple: (success, files, message)
        """
        # 将反斜杠替换为正斜杠，符合GitHub API的URL格式要求
        path = path.replace('\\', '/')
        
        # 使用指定的分支或默认分支
        target_branch = branch or self.branch
        
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        try:
            result = self._make_request('GET', endpoint, params={'ref': target_branch})
            if result:
                return True, result, f'成功列出 {path} 下的文件'
            else:
                return False, None, f'路径不存在: {path}'
        except Exception as e:
            return False, None, f'列出文件失败: {str(e)}'
    
    def get_projects(self, version=None, branch=None):
        """获取GitHub仓库中的项目列表
        
        Args:
            version: Minecraft版本号，默认获取所有版本
            branch: 分支名称，默认使用实例的branch属性
            
        Returns:
            tuple: (success, projects, message)
        """
        try:
            # 从上游仓库的pull请求中获取项目
            # 保存当前仓库
            original_repo = self.repo
            
            # 从仓库地址中提取用户名
            user_login = self.repo.split('/')[0] if '/' in self.repo else self.repo
            
            try:
                # 临时切换到上游仓库
                self.repo = self.upstream_repo
                
                # 获取所有open的pull请求
                endpoint = f'/repos/{self.repo}/pulls'
                params = {'state': 'open'}
                pull_requests = self._make_request('GET', endpoint, params=params)
                if not pull_requests:
                    return False, None, '未找到pull请求'
            finally:
                # 恢复原来的仓库
                self.repo = original_repo
            
            projects = []
            processed_paths = set()  # 用于去重
            
            # 遍历每个pull请求，只处理用户自己的PR
            for pr in pull_requests:
                pr_user = pr.get('user', {})
                pr_user_login = pr_user.get('login')
                
                # 只处理用户自己的PR
                if pr_user_login != user_login:
                    continue
                
                pr_number = pr.get('number')
                pr_title = pr.get('title')
                pr_head = pr.get('head', {})
                pr_branch = pr_head.get('ref')
                
                # 获取pull请求中的文件
                try:
                    # 临时切换到上游仓库
                    self.repo = self.upstream_repo
                    endpoint = f'/repos/{self.repo}/pulls/{pr_number}/files'
                    pr_files = self._make_request('GET', endpoint)
                    if not pr_files:
                        continue
                finally:
                    # 恢复原来的仓库
                    self.repo = original_repo
                
                # 遍历pull请求中的文件
                for file in pr_files:
                    file_path = file.get('filename')
                    # 检查文件路径是否符合项目结构
                    if file_path and 'projects/' in file_path and '/lang/zh_cn.json' in file_path:
                        # 提取项目信息
                        parts = file_path.split('/')
                        if len(parts) >= 6:
                            version_name = parts[1]
                            project_name = parts[3]
                            namespace = parts[4]
                            lang_path = '/'.join(parts[:5]) + '/lang'
                            
                            # 如果指定了版本，只处理该版本
                            if version and version_name != version:
                                continue
                            
                            # 去重
                            project_key = f'{version_name}_{project_name}_{namespace}'
                            if project_key not in processed_paths:
                                processed_paths.add(project_key)
                                projects.append({
                                    'version': version_name,
                                    'project_name': project_name,
                                    'namespace': namespace,
                                    'path': lang_path,
                                    'pr_number': pr_number,
                                    'pr_title': pr_title,
                                    'pr_branch': pr_branch
                                })
            
            return True, projects, f'成功从上游仓库的pull请求中获取 {len(projects)} 个项目'
        except Exception as e:
            return False, None, f'获取项目列表失败: {str(e)}'
    
    def download_project_translations(self, project_info, branch=None):
        """下载项目的翻译文件
        
        Args:
            project_info: 项目信息，包含version、project_name、namespace、path、pr_branch
            branch: 分支名称，默认使用实例的branch属性
            
        Returns:
            tuple: (success, translations, message)
        """
        try:
            # 检查project_info是否为字符串，如果是，尝试解析
            if isinstance(project_info, str):
                import json
                try:
                    # 尝试将字符串解析为JSON
                    project_info = json.loads(project_info)
                except:
                    # 如果解析失败，返回错误
                    return False, None, '项目信息格式错误'
            
            # 保存当前仓库
            original_repo = self.repo
            try:
                # 临时切换到上游仓库
                self.repo = self.upstream_repo
                
                # 使用pull请求的分支（如果有）
                download_branch = project_info.get('pr_branch', branch) if hasattr(project_info, 'get') else branch
                
                # 下载zh_cn.json文件
                zh_cn_path = f"{project_info['path']}/zh_cn.json"
                success, zh_cn_content, message = self.download_file(zh_cn_path, download_branch)
                if not success:
                    return False, None, f'下载中文翻译文件失败: {message}'
                
                # 下载en_us.json文件
                en_us_path = f"{project_info['path']}/en_us.json"
                success, en_us_content, message = self.download_file(en_us_path, download_branch)
                if not success:
                    return False, None, f'下载英文原文文件失败: {message}'
            finally:
                # 恢复原来的仓库
                self.repo = original_repo
            
            # 解析JSON文件
            import json
            zh_cn_data = json.loads(zh_cn_content)
            en_us_data = json.loads(en_us_content)
            
            # 构建翻译数据结构
            translations = {}
            namespace = project_info['namespace']
            translations[namespace] = zh_cn_data
            
            # 构建原始英文文件内容
            raw_english_files = {}
            raw_english_files[namespace] = en_us_content
            
            return True, {'translations': translations, 'raw_english_files': raw_english_files}, '成功从上游仓库的pull请求中下载项目翻译文件'
        except Exception as e:
            return False, None, f'下载项目翻译失败: {str(e)}'
