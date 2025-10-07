"""
Streamlit app: GitHub PPT Browser (Simplified + In-Browser Preview)

Features:
- Default GitHub directory URL embedded.
- Automatically lists PPT files on load.
- Optional Personal Access Token for private repos / higher rate limits.
- Optional recursive search.
- **Open in browser** preview using Microsoft Office Online viewer (opens in a new tab).

Notes & limitations:
- Office Online viewer requires the PPT file to be accessible from the public internet (i.e., a raw GitHub download URL). Private repos won't preview unless the file is publicly reachable.
- If preview fails for private files, users can still download the file using the Download button.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_github_ppt_browser.py
"""

import requests
import streamlit as st
from typing import List, Dict
from urllib.parse import quote_plus

# ----------------------------- Configuration -----------------------------
# Set this to the directory in your repo that contains PPT files
DEFAULT_GITHUB_URL = "https://github.com/your-username/ppt-files-demo/tree/main/presentations"
PPT_EXTS = (".ppt", ".pptx", ".pptm", ".pot", ".potx", ".pps", ".ppsx")

# ----------------------------- Helpers -----------------------------

def parse_github_dir_url(url: str) -> List[str]:
    parts = url.split('/tree/')
    repo_info = parts[0].replace('https://github.com/', '').split('/')
    branch_path = parts[1] if len(parts) > 1 else ''
    branch_parts = branch_path.split('/', 1)
    branch = branch_parts[0] if branch_parts else 'main'
    path = branch_parts[1] if len(branch_parts) > 1 else ''
    return repo_info[0], repo_info[1], branch, path


def github_api_list_contents(owner: str, repo: str, path: str = '', branch: str = 'main', token: str = None) -> List[Dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}" if path else f"https://api.github.com/repos/{owner}/{repo}/contents"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(url, params={"ref": branch}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return [data]
    return data


def filter_ppt_files(items: List[Dict]) -> List[Dict]:
    return [f for f in items if f.get('type')=='file' and f.get('name','').lower().endswith(PPT_EXTS)]

# ----------------------------- Streamlit UI -----------------------------

st.set_page_config(page_title="GitHub PPT Browser", layout="wide")
st.title("GitHub PPT Browser — list, preview & download PPT files")

with st.sidebar:
    st.header("Settings")
    st.markdown("Optional: Personal Access Token (for private repos or higher API limits)")
    token = st.text_input("GitHub token (PAT)", type="password")
    show_all_levels = st.checkbox("Search recursively (including subdirectories)", value=False)

# Parse GitHub URL and list files
owner, repo, branch, path = parse_github_dir_url(DEFAULT_GITHUB_URL)

with st.spinner("Listing PPT files from GitHub..."):
    try:
        if show_all_levels:
            collected = []
            stack = [path or '']
            visited = set()
            while stack:
                current = stack.pop()
                items = github_api_list_contents(owner, repo, current, branch, token)
                for entry in items:
                    if entry.get('type') == 'dir' and entry.get('path') not in visited:
                        visited.add(entry.get('path'))
                        stack.append(entry.get('path'))
                    elif entry.get('type') == 'file' and entry.get('name','').lower().endswith(PPT_EXTS):
                        collected.append(entry)
            files = collected
        else:
            items = github_api_list_contents(owner, repo, path, branch, token)
            files = filter_ppt_files(items)

        if not files:
            st.info("No PPT files found.")
        else:
            st.success(f"Found {len(files)} PPT file(s)")
            for f in files:
                cols = st.columns([4,1,3])
                with cols[0]:
                    st.markdown(f"**[{f['name']}]({f['html_url']})**")
                    st.caption(f"Path: {f['path']}")
                with cols[1]:
                    st.write(f"{f.get('size',0):,} bytes")
                with cols[2]:
                    download_url = f.get('download_url')
                    # Download button
                    if download_url:
                        try:
                            r = requests.get(download_url, stream=True, timeout=30)
                            r.raise_for_status()
                            st.download_button(label="Download", data=r.content, file_name=f['name'], mime="application/vnd.ms-powerpoint")
                        except Exception as e:
                            st.error(f"Failed to fetch file for download: {e}")

                    # Open-in-browser preview (Microsoft Office Online)
                    if download_url:
                        encoded = quote_plus(download_url)
                        viewer_url = f"https://view.officeapps.live.com/op/view.aspx?src={encoded}"
                        # Render a link that opens in a new tab
                        st.markdown(f"[Open in browser (preview)]({viewer_url}){{:target=\"_blank\"}}", unsafe_allow_html=True)
                    else:
                        st.write("")

    except Exception as e:
        st.error(f"Error fetching files: {e}")

st.markdown("---")
st.write("Built with ❤️ — Streamlit")
