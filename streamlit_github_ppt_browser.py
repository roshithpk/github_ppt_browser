"""
Streamlit app: GitHub PPT Browser (Sidebar URL input, Download only)

Features:
- GitHub folder URL is entered in the sidebar (left side).
- Lists .ppt/.pptx files in that folder (optional recursive search).
- Provides a Download button for each file (no preview).
- Optional GitHub Personal Access Token for private repos / higher rate limits.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_github_ppt_browser_user_url.py
"""

import requests
import streamlit as st
from urllib.parse import urlparse
from typing import List, Dict, Optional

PPT_EXTS = (".ppt", ".pptx", ".pptm", ".pot", ".potx", ".pps", ".ppsx")

# ----------------------------- Helpers -----------------------------

def parse_github_dir_url(url: str) -> Optional[Dict[str, str]]:
    """Parse a GitHub directory URL into owner, repo, branch, path.
    Accepts URLs like:
      - https://github.com/owner/repo/tree/branch/path/to/dir
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/branch
    Returns None if parsing fails.
    """
    try:
        parsed = urlparse(url.strip())
        if parsed.netloc not in ("github.com", "www.github.com"):
            return None
        parts = [p for p in parsed.path.split('/') if p]
        if len(parts) < 2:
            return None
        owner = parts[0]
        repo = parts[1]
        branch = 'main'
        path = ''
        if len(parts) >= 3 and parts[2] == 'tree':
            if len(parts) >= 4:
                branch = parts[3]
            if len(parts) >= 5:
                path = '/'.join(parts[4:])
        return {"owner": owner, "repo": repo, "branch": branch, "path": path}
    except Exception:
        return None


def github_api_list_contents(owner: str, repo: str, path: str = '', branch: str = 'main', token: Optional[str] = None) -> List[Dict]:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}" if path else f"https://api.github.com/repos/{owner}/{repo}/contents"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(api_url, params={"ref": branch}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [data] if isinstance(data, dict) else data


def filter_ppt_files(items: List[Dict]) -> List[Dict]:
    return [it for it in items if it.get('type')=='file' and it.get('name','').lower().endswith(PPT_EXTS)]


def walk_and_collect_ppts(owner: str, repo: str, start_path: str, branch: str, token: Optional[str]) -> List[Dict]:
    collected = []
    stack = [start_path or '']
    visited = set()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    while stack:
        current = stack.pop()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{current}" if current else f"https://api.github.com/repos/{owner}/{repo}/contents"
        resp = requests.get(api_url, params={"ref": branch}, headers=headers, timeout=30)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        for entry in data:
            if entry.get('type') == 'dir':
                dirpath = entry.get('path')
                if dirpath not in visited:
                    visited.add(dirpath)
                    stack.append(dirpath)
            elif entry.get('type') == 'file' and entry.get('name','').lower().endswith(PPT_EXTS):
                collected.append(entry)
    return collected


# ----------------------------- Streamlit UI -----------------------------

st.set_page_config(page_title="GitHub PPT Browser", layout="wide")
st.title("GitHub PPT Browser — paste a GitHub folder URL (sidebar)")

# Sidebar inputs (left side)
with st.sidebar:
    st.header("Repository settings")
    github_url = st.text_input("GitHub folder URL", help="e.g. https://github.com/owner/repo/tree/main/presentations")
    token = st.text_input("GitHub token (PAT - optional)", type="password", help="Needed for private repos or higher rate limits")
    show_all_levels = st.checkbox("Search recursively (include subdirectories)", value=False)
    list_btn = st.button("List PPT files")

# Main area: results will appear here
if list_btn:
    if not github_url:
        st.error("Please enter the GitHub folder URL in the left sidebar.")
    else:
        parsed = parse_github_dir_url(github_url)
        if not parsed:
            st.error("Could not parse the GitHub URL. Make sure it's a valid GitHub repository or folder URL.")
        else:
            owner = parsed['owner']
            repo = parsed['repo']
            branch = parsed.get('branch','main')
            path = parsed.get('path','')

            st.subheader(f"Repository: {owner}/{repo}  (branch: {branch})")
            if path:
                st.caption(f"Path: {path}")

            with st.spinner("Fetching files from GitHub..."):
                try:
                    if show_all_levels:
                        files = walk_and_collect_ppts(owner, repo, path, branch, token or None)
                    else:
                        items = github_api_list_contents(owner, repo, path, branch, token or None)
                        files = filter_ppt_files(items)

                    if not files:
                        st.info("No PPT files found in the specified folder.")
                    else:
                        st.success(f"Found {len(files)} PPT file(s)")
                        for f in files:
                            c1, c2 = st.columns([5,2])
                            with c1:
                                st.markdown(f"**{f['name']}**")
                                st.caption(f"Path: {f.get('path')}")
                            with c2:
                                download_url = f.get('download_url')
                                if download_url:
                                    try:
                                        r = requests.get(download_url, stream=True, timeout=30)
                                        r.raise_for_status()
                                        st.download_button(label="Download", data=r.content, file_name=f['name'], mime="application/vnd.ms-powerpoint")
                                    except Exception as e:
                                        st.error(f"Failed to fetch file for download: {e}")

                except requests.HTTPError as he:
                    status = getattr(he.response, 'status_code', None)
                    if status == 404:
                        st.error("Repository or path not found. Check the URL and branch/path.")
                    elif status == 403:
                        st.error("Access forbidden or rate-limited by GitHub API. Consider adding a Personal Access Token in the sidebar.")
                    else:
                        st.error(f"GitHub API error: {he}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

st.markdown("---")
st.write("Built by Roshith")
