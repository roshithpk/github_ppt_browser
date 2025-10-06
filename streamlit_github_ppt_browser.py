"""
Streamlit app: GitHub PPT Browser

What it does:
- Let user enter a GitHub directory URL or owner/repo/path/branch
- Lists .ppt/.pptx (and similar) files in that directory
- Shows file size and a Download button for each file (fetches file bytes and serves via Streamlit)
- Supports optional GitHub Personal Access Token for private repos / higher rate limits

Run:
    pip install streamlit requests
    streamlit run streamlit_github_ppt_browser.py

Notes:
- For large PPT files this will download to the Streamlit server before offering to the user.
- If you expect very large files or many files, consider streaming download or adding size limits.
"""

import re
import requests
from urllib.parse import urlparse
import streamlit as st
from typing import Optional, Tuple, List, Dict

# ----------------------------- Helpers -----------------------------

def parse_github_dir_url(url: str) -> Optional[Tuple[str, str, str, str]]:
    """Parse a GitHub directory URL into (owner, repo, branch, path).
    Examples accepted:
      - https://github.com/owner/repo/tree/branch/path/to/dir
      - https://github.com/owner/repo/tree/branch
      - https://github.com/owner/repo
    If branch/path are missing, returns None for those values.
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc not in ("github.com", "www.github.com"):
            return None
        parts = [p for p in parsed.path.split("/") if p]
        # minimal: ['owner', 'repo']
        if len(parts) < 2:
            return None
        owner = parts[0]
        repo = parts[1]
        branch = "main"
        path = ""
        # look for 'tree' indicating branch + path
        if len(parts) >= 3 and parts[2] == "tree":
            if len(parts) >= 4:
                branch = parts[3]
            if len(parts) >= 5:
                path = "/".join(parts[4:])
        return owner, repo, branch, path
    except Exception:
        return None


def github_api_list_contents(owner: str, repo: str, path: str = "", branch: str = "main", token: Optional[str] = None) -> List[Dict]:
    """Return the JSON list of contents from GitHub API for a given directory.
    Raises requests.HTTPError on failure.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}" if path else f"https://api.github.com/repos/{owner}/{repo}/contents"
    params = {"ref": branch}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(api_url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # if the path points to a file, GitHub returns a dict; convert to list
    if isinstance(data, dict):
        return [data]
    return data


PPT_EXTS = (".ppt", ".pptx", ".pptm", ".pot", ".potx", ".pps", ".ppsx")


def filter_ppt_files(items: List[Dict]) -> List[Dict]:
    """From the GitHub API contents list, return only file entries that are PPT types."""
    result = []
    for it in items:
        if it.get("type") != "file":
            continue
        name = it.get("name", "")
        if name.lower().endswith(PPT_EXTS):
            result.append({
                "name": name,
                "path": it.get("path"),
                "size": it.get("size", 0),
                "download_url": it.get("download_url"),
                "html_url": it.get("html_url"),
            })
    return result


@st.cache_data(show_spinner=False)
def list_ppt_in_github(owner: str, repo: str, path: str, branch: str, token: Optional[str]) -> List[Dict]:
    items = github_api_list_contents(owner, repo, path=path or "", branch=branch or "main", token=token)
    # GitHub API returns contents of the directory; if path is a subdirectory, it returns that list
    # But if the directory contains subdirectories, those entries will be type 'dir'. We only want files at this level.
    return filter_ppt_files(items)


# ----------------------------- Streamlit UI -----------------------------

st.set_page_config(page_title="GitHub PPT Browser", layout="wide")
st.title("GitHub PPT Browser — list & download PPT files from a repo directory")

with st.sidebar:
    st.header("Repo / Directory settings")
    github_url = st.text_input("GitHub directory URL (e.g. https://github.com/owner/repo/tree/branch/path)")

    col1, col2 = st.columns(2)
    with col1:
        owner_input = st.text_input("Owner (user or org)")
        repo_input = st.text_input("Repo")
    with col2:
        branch_input = st.text_input("Branch", value="main")
        path_input = st.text_input("Path inside repo (leave empty for root)")

    st.markdown("---")
    st.markdown("Personal Access Token (optional):\nUse if repo is private or to increase rate limits.")
    token = st.text_input("GitHub token (PAT)", type="password")

    st.markdown("---")
    show_all_levels = st.checkbox("Search recursively (will walk through subdirectories)", value=False)
    fetch_btn = st.button("List PPT files")

# If user provided a GitHub URL, try to parse it and prefill fields
if github_url:
    parsed = parse_github_dir_url(github_url)
    if parsed:
        owner_parsed, repo_parsed, branch_parsed, path_parsed = parsed
        # Only prefill fields if they are empty to avoid overwriting user edits
        if not owner_input:
            owner_input = owner_parsed
        if not repo_input:
            repo_input = repo_parsed
        if not branch_input or branch_input == "main":
            branch_input = branch_parsed
        if not path_input:
            path_input = path_parsed


# Helper: recursively walk directory using GitHub API

def walk_and_collect_ppts(owner: str, repo: str, path: str, branch: str, token: Optional[str]) -> List[Dict]:
    collected = []
    stack = [path or ""]
    visited_dirs = set()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    while stack:
        current = stack.pop()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{current}" if current else f"https://api.github.com/repos/{owner}/{repo}/contents"
        params = {"ref": branch}
        resp = requests.get(api_url, params=params, headers=headers, timeout=30)
        if resp.status_code == 404:
            # skip missing path
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        for entry in data:
            etype = entry.get("type")
            if etype == "dir":
                dirpath = entry.get("path")
                if dirpath not in visited_dirs:
                    visited_dirs.add(dirpath)
                    stack.append(dirpath)
            elif etype == "file":
                name = entry.get("name", "")
                if name.lower().endswith(PPT_EXTS):
                    collected.append({
                        "name": name,
                        "path": entry.get("path"),
                        "size": entry.get("size", 0),
                        "download_url": entry.get("download_url"),
                        "html_url": entry.get("html_url"),
                    })
    return collected


# Main listing logic
if fetch_btn:
    if not owner_input or not repo_input:
        st.error("Please provide at minimum the repository owner and repo name (or paste a valid GitHub URL).")
    else:
        owner = owner_input.strip()
        repo = repo_input.strip()
        branch = branch_input.strip() if branch_input else "main"
        path = path_input.strip()

        with st.spinner("Listing files from GitHub..."):
            try:
                if show_all_levels:
                    files = walk_and_collect_ppts(owner, repo, path, branch, token or None)
                else:
                    files = list_ppt_in_github(owner, repo, path, branch, token or None)

                if not files:
                    st.info("No PPT files found in the specified directory.")
                else:
                    st.success(f"Found {len(files)} PPT file(s)")

                    # Display a table and provide download buttons per file
                    for f in files:
                        cols = st.columns([4, 1, 2])
                        with cols[0]:
                            st.markdown(f"**[{f['name']}]({f['html_url']})**")
                            st.caption(f"Path: {f['path']}")
                        with cols[1]:
                            st.write(f"{f['size']:,} bytes")
                        with cols[2]:
                            download_url = f.get("download_url")
                            if download_url:
                                try:
                                    r = requests.get(download_url, stream=True, timeout=60)
                                    r.raise_for_status()
                                    data = r.content
                                    st.download_button(label="Download", data=data, file_name=f['name'], mime="application/vnd.ms-powerpoint")
                                except Exception as e:
                                    st.error(f"Failed to fetch file for download: {e}")
                            else:
                                st.warning("No direct download URL available for this item.")

            except requests.HTTPError as he:
                status = getattr(he.response, 'status_code', None)
                if status == 404:
                    st.error("Repository or path not found. Check the owner, repo, branch and path.")
                elif status == 403:
                    st.error("Access forbidden or rate-limited by GitHub API. Consider adding a Personal Access Token in the sidebar.")
                else:
                    st.error(f"GitHub API error: {he}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

# Small helper to show example usage
st.markdown("---")
st.markdown("**Quick start:** Paste a GitHub directory URL or type owner/repo. Example URL format: `https://github.com/owner/repo/tree/main/path/to/dir`\n\nIf the repo is private, provide a Personal Access Token in the sidebar.")


# Footer
st.write("Built with ❤️ — Streamlit. If you want enhancements (e.g., show previews, sort/filter, bulk download as zip), tell me what you need!")

