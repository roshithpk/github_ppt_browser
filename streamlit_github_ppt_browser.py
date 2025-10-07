"""
Streamlit app: GitHub PPT Browser (User-entered URL)

Features:
- User pastes a GitHub folder URL into the app.
- Lists .ppt/.pptx files in that folder (optionally recursive).
- Download button for each file.
- Open-in-browser preview via Microsoft Office Online viewer (and optional inline iframe preview).
- Optional GitHub Personal Access Token for private repos / higher rate limits.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_github_ppt_browser_user_url.py
"""

import requests
import streamlit as st
from urllib.parse import urlparse, quote_plus
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
st.title("GitHub PPT Browser — paste a GitHub folder URL")

st.markdown("Paste a GitHub folder URL that contains PowerPoint files (e.g., `https://github.com/owner/repo/tree/main/presentations`).")

github_url = st.text_input("GitHub folder URL")

with st.sidebar:
    st.header("Options")
    token = st.text_input("GitHub token (PAT - optional)", type="password")
    show_all_levels = st.checkbox("Search recursively (include subdirectories)", value=False)
    inline_preview = st.checkbox("Attempt inline preview (iframe)", value=True)
    list_btn = st.button("List PPT files")

if list_btn:
    if not github_url:
        st.error("Please paste a GitHub folder URL.")
    else:
        parsed = parse_github_dir_url(github_url)
        if not parsed:
            st.error("Could not parse the GitHub URL. Make sure it's a valid GitHub repository or folder URL.")
        else:
            owner = parsed['owner']
            repo = parsed['repo']
            branch = parsed.get('branch','main')
            path = parsed.get('path','')

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
                            c1, c2, c3 = st.columns([4,1,3])
                            with c1:
                                st.markdown(f"**[{f['name']}]({f.get('html_url')})**")
                                st.caption(f"Path: {f.get('path')}")
                            with c2:
                                st.write(f"{f.get('size',0):,} bytes")
                            with c3:
                                download_url = f.get('download_url')
                                if download_url:
                                    try:
                                        r = requests.get(download_url, stream=True, timeout=30)
                                        r.raise_for_status()
                                        st.download_button(label="Download", data=r.content, file_name=f['name'], mime="application/vnd.ms-powerpoint")
                                    except Exception as e:
                                        st.error(f"Failed to fetch file for download: {e}")

                                # Preview via Office Online
                                if download_url:
                                    viewer = f"https://view.officeapps.live.com/op/view.aspx?src={quote_plus(download_url)}"
                                    if inline_preview:
                                        try:
                                            st.markdown("<details><summary>Preview (expand)</summary>", unsafe_allow_html=True)
                                            iframe = f'<iframe src="{viewer}" width="100%" height="600px" frameborder="0"></iframe>'
                                            st.components.v1.html(iframe, height=600, scrolling=True)
                                            st.markdown("</details>", unsafe_allow_html=True)
                                        except Exception:
                                            st.markdown(f"[Open preview in new tab]({viewer})")
                                    else:
                                        st.markdown(f"[Open preview in new tab]({viewer})")

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
st.write("Built with ❤️ — Streamlit")
