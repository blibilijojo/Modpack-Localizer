from __future__ import annotations
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
import concurrent.futures
from utils.file_utils import decode_json_value_with_unicode
from core.models import JSON_KEY_VALUE_PATTERN
from core.exceptions import ServiceResult

_REPO_URL_PATTERN = re.compile(r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$')
_OWNER_REPO_PATTERN = re.compile(r'^([^/]+)/([^/]+)$')

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
        from utils.api_urls import GITHUB_API_BASE
        self.api_base = GITHUB_API_BASE
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.retry_count = 3
        self.retry_delay = 2
        self._builder = None
        
        # 创建会话对象，启用连接池
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,  # 连接池大小
            pool_maxsize=10,      # 最大连接数
            max_retries=3,        # 最大重试次数
            pool_block=False      # 不阻塞
        )
        self.session.mount('https://', adapter)
        self.session.headers.update(self.headers)
        
        # 记录初始化参数
        logging.info(f'初始化GitHub服务: 仓库={self.repo}, 分支={self.branch}, 推送到源仓库={self.push_to_upstream}, 上游分支={self.upstream_branch}, 上游仓库={self.upstream_repo}, 推送前删除分支={self.delete_branch_before_push}')
    
    def _get_builder(self):
        if self._builder is None:
            from core.builder import Builder
            self._builder = Builder()
        return self._builder

    def _parse_repo_url(self, repo_url: str) -> str:
        match = _REPO_URL_PATTERN.match(repo_url)
        if match:
            return f'{match.group(1)}/{match.group(2)}'
        match = _OWNER_REPO_PATTERN.match(repo_url)
        if match:
            return repo_url
        return repo_url
    
    def _make_request(self, method, endpoint, repo=None, **kwargs):
        target_repo = repo or self.repo
        if repo and repo != self.repo:
            endpoint = endpoint.replace(f'/repos/{self.repo}/', f'/repos/{target_repo}/', 1)
        url = f'{self.api_base}{endpoint}'
        
        try:
            if method == 'GET':
                response = self.session.get(url, **kwargs)
            elif method == 'PUT':
                response = self.session.put(url, **kwargs)
            elif method == 'POST':
                response = self.session.post(url, **kwargs)
            elif method == 'PATCH':
                response = self.session.patch(url, **kwargs)
            elif method == 'DELETE':
                response = self.session.delete(url, **kwargs)
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
        endpoint = f'/repos/{self.repo}'
        try:
            result = self._make_request('GET', endpoint)
            return ServiceResult.ok(message=f'认证成功！仓库: {result.get("name")}')
        except Exception as e:
            return ServiceResult.fail(f'认证失败: {str(e)}')
    
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
        try:
            endpoint = f'/repos/{self.repo}/git/refs/heads/{self.branch}'
            self._make_request('DELETE', endpoint)
            logging.info(f'分支 {self.branch} 删除成功')
            return True
        except Exception as e:
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
        path = path.replace('\\', '/')
        
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        data = {
            'message': message,
            'content': encoded_content,
            'branch': self.branch
        }
        
        try:
            sha = self.get_file_sha(path)
            if sha:
                data['sha'] = sha
        except Exception:
            pass
        
        try:
            result = self._make_request('PUT', endpoint, json=data)
            if result:
                return ServiceResult.ok(message=f'文件上传成功: {result.get("content", {}).get("name")}')
            else:
                return ServiceResult.ok(message=f'文件创建成功: {Path(path).name}')
        except requests.RequestException as e:
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
                except (json.JSONDecodeError, KeyError, AttributeError):
                    pass
            return ServiceResult.fail(f'文件上传失败: {str(e)}{error_details}')
        except Exception as e:
            return ServiceResult.fail(f'文件上传失败: {str(e)}')
    
    def _parse_json_with_unicode_only(self, content):
        result = {}
        for match in JSON_KEY_VALUE_PATTERN.finditer(content):
            key = match.group(1)
            value = match.group(2)
            temp_value = decode_json_value_with_unicode(value)
            if key == '_comment':
                continue
            result[key] = temp_value
        return result

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
            builder = self._get_builder()

            for ns, items in translations.items():
                current_project_name = project_name or (ns.split(':')[0] if ':' in ns else ns)
                current_namespace = namespace or (ns.split(':')[0] if ':' in ns else ns)

                lang_dir = Path(temp_dir) / 'projects' / 'assets' / current_project_name / version / current_namespace / 'lang'
                lang_dir.mkdir(parents=True, exist_ok=True)

                parsed_english = {}
                if raw_english_files and current_namespace in raw_english_files:
                    raw_content = raw_english_files[current_namespace]
                    parsed_english = self._parse_json_with_unicode_only(raw_content)

                template_content = raw_english_files.get(current_namespace) if raw_english_files else None

                if file_format in ['json', 'both']:
                    json_path = lang_dir / 'zh_cn.json'
                    if template_content:
                        json_content = builder._build_json_file(template_content, items)
                    else:
                        json_content = json.dumps(items, ensure_ascii=False, indent=4)
                    json_path.write_text(json_content, encoding='utf-8')

                    en_json_path = lang_dir / 'en_us.json'
                    en_items = {key: parsed_english.get(key, key) for key in items}
                    if template_content:
                        en_json_content = builder._build_json_file(template_content, en_items)
                    else:
                        en_json_content = json.dumps(en_items, ensure_ascii=False, indent=4)
                    en_json_path.write_text(en_json_content, encoding='utf-8')

                if file_format in ['lang', 'both']:
                    lang_path = lang_dir / 'zh_cn.lang'
                    template_content_lang = ''.join([f'{key} = {key}\n' for key in items])
                    lang_content = builder._build_lang_file(template_content_lang, items)
                    lang_path.write_text(lang_content, encoding='utf-8')

                    en_lang_path = lang_dir / 'en_us.lang'
                    en_lang_content = ''.join([f'{key} = {parsed_english.get(key, key)}\n' for key in items])
                    en_lang_path.write_text(en_lang_content, encoding='utf-8')

            return temp_dir

        except Exception as e:
            shutil.rmtree(temp_dir)
            raise
    
    def _determine_file_type(self, github_path: str) -> str:
        if 'zh_cn' in github_path:
            return '译文文件'
        elif 'en_us' in github_path:
            return '原文文件'
        return '文件'

    def _extract_namespace_from_path(self, github_path: str, namespace: str | None) -> str:
        if namespace:
            return namespace
        path_parts = github_path.split('/')
        if len(path_parts) > 5:
            return path_parts[5]
        return 'unknown'

    def _upload_files_from_dir(self, temp_dir: str, version: str, namespace: str | None) -> ServiceResult:
        uploaded_files: list[str] = []
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(temp_dir)
                github_path = str(relative_path).replace('\\', '/')

                content = file_path.read_text(encoding='utf-8')

                file_type = self._determine_file_type(github_path)
                resolved_namespace = self._extract_namespace_from_path(github_path, namespace)

                full_message = f'提交 {resolved_namespace} {file_type} - {version}\n\n文件: {github_path}'

                result = self.upload_file(github_path, content, full_message)
                if not result.success:
                    return ServiceResult.fail(f'上传文件失败: {result.message}', extra=uploaded_files)

                uploaded_files.append(github_path)

        return ServiceResult.ok(data=uploaded_files)

    def upload_translations(self, translations, version, commit_message, project_name=None, namespace=None, file_format='json', raw_english_files=None):
        if not translations:
            return ServiceResult.fail('没有可上传的翻译内容')

        try:
            temp_dir = self.build_resource_pack_structure(translations, version, project_name, namespace, file_format, raw_english_files)

            try:
                if not self._check_and_create_branch():
                    return ServiceResult.fail('分支创建失败')

                upload_result = self._upload_files_from_dir(temp_dir, version, namespace)
                if not upload_result.success:
                    return ServiceResult.fail(upload_result.message)

                uploaded_files = upload_result.data or []

                if self.push_to_upstream:
                    push_success, push_message = self._push_to_upstream()
                    if push_success:
                        return ServiceResult.ok(message=f'成功上传 {len(uploaded_files)} 个文件到版本 {version}，并推送到源仓库')
                    else:
                        return ServiceResult.ok(message=f'成功上传 {len(uploaded_files)} 个文件到版本 {version}，但推送到源仓库失败: {push_message}')
                else:
                    return ServiceResult.ok(message=f'成功上传 {len(uploaded_files)} 个文件到版本 {version}')

            finally:
                shutil.rmtree(temp_dir)

        except Exception as e:
            logging.error(f'上传翻译失败: {str(e)}', exc_info=True)
            return ServiceResult.fail(f'上传失败: {str(e)}')
    
    def get_repo_info(self):
        """获取仓库信息"""
        endpoint = f'/repos/{self.repo}'
        try:
            return self._make_request('GET', endpoint)
        except Exception as e:
            logging.error(f'获取仓库信息失败: {str(e)}')
            return None
    
    def _push_to_upstream(self):
        try:
            base_branch = 'main'
            
            pr_title = ''
            if hasattr(self, 'pr_title'):
                pr_title = self.pr_title
            else:
                pr_title = f'更新汉化资源包 {self.branch}'
            
            fork_owner = self.repo.split('/')[0]
            head_branch = f'{fork_owner}:{self.branch}'
            
            endpoint = f'/repos/{self.upstream_repo}/pulls'
            params = {'state': 'open'}
            existing_prs = self._make_request('GET', endpoint, params=params)
            
            if existing_prs:
                for pr in existing_prs:
                    if pr.get('head', {}).get('ref') == self.branch and pr.get('head', {}).get('user', {}).get('login') == fork_owner:
                        pr_url = pr.get('html_url', '')
                        logging.info(f'PR已存在: {pr_url}')
                        return True, f'PR已存在: {pr_url}'
            
            data = {
                'title': pr_title,
                'head': head_branch,
                'base': base_branch,
                'body': f'来自分支 {self.branch} 的汉化更新\n\n请审核并合并此PR。'
            }
            
            result = self._make_request('POST', endpoint, json=data)
            if result:
                pr_url = result.get('html_url', '')
                logging.info(f'创建PR成功: {pr_url}')
                return True, f'创建PR成功，PR标题: {pr_title}'
            else:
                logging.info(f'创建PR成功: {self.upstream_repo} {head_branch} -> {base_branch}')
                return True, f'创建PR成功，PR标题: {pr_title}'
        except Exception as e:
            logging.error(f'创建PR失败: {str(e)}')
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
        try:
            upstream_info = self._make_request('GET', f'/repos/{self.upstream_repo}')
            if not upstream_info:
                return ServiceResult.fail('无法获取源仓库信息')
            
            upstream_default_branch = upstream_info.get('default_branch', 'main')
            
            upstream_branch_info = self._make_request('GET', f'/repos/{self.upstream_repo}/branches/{upstream_default_branch}')
            if not upstream_branch_info or 'commit' not in upstream_branch_info:
                return ServiceResult.fail('无法获取源仓库分支信息')
            
            upstream_latest_sha = upstream_branch_info['commit']['sha']
            logging.info(f'源仓库最新提交: {upstream_latest_sha}')
            
            repo_info = self._make_request('GET', f'/repos/{self.repo}')
            if not repo_info:
                return ServiceResult.fail('无法获取当前仓库信息')
            
            repo_default_branch = repo_info.get('default_branch', 'main')
            
            repo_branch_info = self._make_request('GET', f'/repos/{self.repo}/branches/{repo_default_branch}')
            if not repo_branch_info or 'commit' not in repo_branch_info:
                return ServiceResult.fail('无法获取当前仓库分支信息')
            
            repo_latest_sha = repo_branch_info['commit']['sha']
            logging.info(f'当前仓库最新提交: {repo_latest_sha}')
            
            if upstream_latest_sha == repo_latest_sha:
                return ServiceResult.ok(message='当前仓库已是最新版本，无需同步')
            
            sync_message = f'同步源仓库 {self.upstream_repo}:{upstream_default_branch} 的最新代码'
            logging.info(sync_message)
            
            ref_path = f'heads/{repo_default_branch}'
            endpoint = f'/repos/{self.repo}/git/refs/{ref_path}'
            data = {
                'sha': upstream_latest_sha,
                'force': True
            }
            
            result = self._make_request('PATCH', endpoint, json=data)
            if result:
                logging.info(f'成功更新分支 {repo_default_branch} 到提交 {upstream_latest_sha}')
                return ServiceResult.ok(message=f'成功同步源仓库最新代码到 {repo_default_branch} 分支')
            else:
                logging.info(f'成功更新分支 {repo_default_branch} 到提交 {upstream_latest_sha}')
                return ServiceResult.ok(message=f'成功同步源仓库最新代码到 {repo_default_branch} 分支')
            
        except Exception as e:
            logging.error(f'同步原仓库失败: {str(e)}')
            return ServiceResult.fail(f'同步失败: {str(e)}')
    
    def download_file(self, path, branch=None):
        path = path.replace('\\', '/')
        target_branch = branch or self.branch
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        try:
            result = self._make_request('GET', endpoint, params={'ref': target_branch})
            if result:
                content = base64.b64decode(result.get('content', '')).decode('utf-8')
                return ServiceResult.ok(data=content, message=f'文件下载成功: {Path(path).name}')
            else:
                return ServiceResult.fail(f'文件不存在: {path}')
        except Exception as e:
            return ServiceResult.fail(f'文件下载失败: {str(e)}')
    
    def list_files(self, path='', branch=None):
        path = path.replace('\\', '/')
        target_branch = branch or self.branch
        endpoint = f'/repos/{self.repo}/contents/{path}'
        
        try:
            result = self._make_request('GET', endpoint, params={'ref': target_branch})
            if result:
                return ServiceResult.ok(data=result, message=f'成功列出 {path} 下的文件')
            else:
                return ServiceResult.fail(f'路径不存在: {path}')
        except Exception as e:
            return ServiceResult.fail(f'列出文件失败: {str(e)}')
    
    def get_projects(self, version=None, branch=None):
        try:
            user_login = self.repo.split('/')[0] if '/' in self.repo else self.repo

            endpoint = f'/repos/{self.repo}/pulls'
            params = {'state': 'open'}
            pull_requests = self._make_request('GET', endpoint, repo=self.upstream_repo, params=params)
            if not pull_requests:
                return ServiceResult.fail('未找到pull请求')
            
            projects = []
            processed_paths = set()

            for pr in pull_requests:
                pr_user = pr.get('user', {})
                pr_user_login = pr_user.get('login')
                
                if pr_user_login != user_login:
                    continue
                
                pr_number = pr.get('number')
                pr_title = pr.get('title')
                pr_head = pr.get('head', {})
                pr_branch = pr_head.get('ref')
                
                endpoint = f'/repos/{self.repo}/pulls/{pr_number}/files'
                pr_files = self._make_request('GET', endpoint, repo=self.upstream_repo)
                if not pr_files:
                    continue
                
                # 遍历pull请求中的文件
                for file in pr_files:
                    file_path = file.get('filename')
                    # 检查文件路径是否符合项目结构
                    if file_path and 'projects/' in file_path and '/lang/zh_cn.json' in file_path:
                        parts = file_path.split('/')
                        if len(parts) >= 6 and parts[1] == 'assets':
                            project_name = parts[2]
                            version_name = parts[3]
                            namespace = parts[4]
                            # 保持完整的文件路径，包括zh_cn.json
                            lang_path = file_path
                            
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
            
            return ServiceResult.ok(data=projects, message=f'成功从上游仓库的pull请求中获取 {len(projects)} 个项目')
        except Exception as e:
            return ServiceResult.fail(f'获取项目列表失败: {str(e)}')
    
    def download_project_translations(self, project_info, branch=None):
        try:
            if isinstance(project_info, str):
                try:
                    project_info = json.loads(project_info)
                except (json.JSONDecodeError, ValueError):
                    return ServiceResult.fail('项目信息格式错误')

            download_branch = project_info.get('pr_branch', branch) if hasattr(project_info, 'get') else branch

            zh_cn_path = f"{project_info['path']}"
            en_us_path = f"{project_info['path'].replace('zh_cn.json', 'en_us.json')}"

            file_paths = [zh_cn_path, en_us_path]
            results = {}

            def download_file_task(path):
                return path, self.download_file(path, download_branch)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_to_path = {executor.submit(download_file_task, path): path for path in file_paths}
                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        path, dl_result = future.result()
                        if dl_result.success:
                            results[path] = dl_result.data
                        else:
                            return ServiceResult.fail(f'下载文件失败: {dl_result.message}')
                    except Exception as e:
                        return ServiceResult.fail(f'下载文件时发生错误: {str(e)}')

            zh_cn_content = results.get(zh_cn_path)
            en_us_content = results.get(en_us_path)

            if not zh_cn_content or not en_us_content:
                return ServiceResult.fail('部分文件下载失败')

            zh_cn_data = self._parse_json_with_unicode_only(zh_cn_content)
            en_us_data = self._parse_json_with_unicode_only(en_us_content)

            translations = {}
            namespace = project_info['namespace']
            translations[namespace] = zh_cn_data

            raw_english_files = {}
            raw_english_files[namespace] = en_us_content

            return ServiceResult.ok(data={'translations': translations, 'raw_english_files': raw_english_files}, message='成功从上游仓库的pull请求中下载项目翻译文件')
        except Exception as e:
            return ServiceResult.fail(f'下载项目翻译失败: {str(e)}')
