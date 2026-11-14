#!/bin/bash
# ==========================================
# 闲鱼自动回复系统 - 一键部署脚本
# 自动检查并安装 Docker/Compose，生成配置并拉取远程镜像启动
# 用法: bash deploy.sh
# ==========================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$WORK_DIR/docker-compose.deploy.yml"
ENV_FILE="$WORK_DIR/.env"

echo "=========================================="
echo "  闲鱼自动回复系统 - 一键部署"
echo "=========================================="
echo ""

# ========== 检查环境 ==========
INSTALL_ROOT=()
DOCKER_PREFIX=()
INSTALL_OS=''
INSTALL_OS_VERSION=''
INSTALL_OS_NAME=''
INSTALL_OS_FULL_VERSION=''
INSTALL_UBUNTU_ARCH=''
INSTALL_UBUNTU_REPO=main
INSTALL_CENTOS_STREAM=0
INSTALL_APT_UPDATED=0

install_error() {
    printf '[错误] %s\n' "$*" >&2
    exit 1
}

# 安装和启动系统服务时使用 root 或免密 sudo，避免 SSH/管道执行等待密码。
require_install_root() {
    if [ "$EUID" -ne 0 ]; then
        command -v sudo >/dev/null 2>&1 && sudo -n true ||
            install_error '自动安装或启动 Docker 需要 root 或免密 sudo，请使用具备权限的账号'
        INSTALL_ROOT=(sudo -n)
    fi
}

install_as_root() {
    "${INSTALL_ROOT[@]}" "$@" </dev/null
}

# 解析或转换 Debian/Ubuntu 的 .list / .sources；$1 模式，$2 源文件，$3 仓库路由表。
process_apt_sources() {
    install_as_root awk -v mode="$1" -v routes="$3" -v deb822="${2##*.}" -v distro="$INSTALL_OS" -v ubuntu_repo="$INSTALL_UBUNTU_REPO" '
        function kind(uri) {
            sub(/\/$/, "", uri)
            if (distro=="ubuntu") {
                if (uri ~ /^mirror:\/\/mirrors\.ubuntu\.com\/mirrors\.txt$/ ||
                    uri ~ /^mirror\+file:\/+etc\/apt\/mirrors\/ubuntu\.list$/) return ubuntu_repo
                if (uri ~ /^mirror\+file:\/+etc\/apt\/mirrors\/ubuntu-ports\.list$/) return "ports"
                if (uri ~ /^(https?|ftp):\/\/old-releases\.ubuntu\.com\/ubuntu$/ ||
                    uri ~ /^https?:\/\/mirrors\.(ustc\.edu\.cn|nju\.edu\.cn)\/ubuntu-old-releases\/ubuntu$/) return ubuntu_repo
                if (uri ~ /^(https?|ftp):\/\/([[:alnum:].-]+\.)?(archive|security)\.ubuntu\.com\/ubuntu$/) return ubuntu_repo
                if (uri ~ /^(https?|ftp):\/\/ports\.ubuntu\.com\/ubuntu-ports$/) return "ports"
                if (uri ~ /^https?:\/\/mirrors\.(tuna\.tsinghua\.edu\.cn|aliyun\.com|huaweicloud\.com|ustc\.edu\.cn|nju\.edu\.cn)\/ubuntu-ports$/) return "ports"
                if (uri ~ /^https?:\/\/mirrors\.(tuna\.tsinghua\.edu\.cn|aliyun\.com|huaweicloud\.com|ustc\.edu\.cn|nju\.edu\.cn)\/ubuntu$/) return ubuntu_repo
                return ""
            }
            if (uri ~ /^mirror\+file:\/+etc\/apt\/mirrors\/debian\.list$/) return "main"
            if (uri ~ /^mirror\+file:\/+etc\/apt\/mirrors\/debian-security\.list$/) return "security"
            if (uri ~ /^(https?|ftp):\/\/security\.debian\.org(\/debian-security)?$/) return "security"
            if (uri ~ /^(https?|ftp):\/\/([[:alnum:].-]+\.)?debian\.org\/debian$/ ||
                uri ~ /^https?:\/\/mirrors\.(tuna\.tsinghua\.edu\.cn|aliyun\.com)\/(debian-archive\/)?debian$/) return "main"
            if (uri ~ /^(https?|ftp):\/\/([[:alnum:].-]+\.)?debian\.org\/debian-security$/ ||
                uri ~ /^https?:\/\/mirrors\.(tuna\.tsinghua\.edu\.cn|aliyun\.com)\/(debian-archive\/)?debian-security$/) return "security"
            return ""
        }
        function field(block, name,    lines,n,i,value,reading) {
            n=split(block,lines,"\n")
            for (i=1;i<=n;i++) {
                if (tolower(lines[i]) ~ "^" tolower(name) ":") {
                    value=lines[i]; sub(/^[^:]+:[[:space:]]*/,"",value); reading=1
                } else if (reading && lines[i] ~ /^[[:space:]]+/) value=value " " lines[i]
                else reading=0
            }
            return value
        }
        function replace_field(block, name, value,    lines,n,i,line,out,reading,found) {
            n=split(block,lines,"\n")
            for (i=1;i<=n;i++) {
                line=lines[i]
                if (tolower(line) ~ "^" tolower(name) ":") {
                    line=name ": " value; reading=1; found=1
                } else if (reading && line ~ /^[[:space:]]+/) continue
                else reading=0
                out=out (out=="" ? "" : "\n") line
            }
            return out (found ? "" : "\n" name ": " value)
        }
        BEGIN {
            if (mode=="rewrite") while ((getline row < routes)>0) {
                split(row,parts,"\t"); key=parts[1] "|" parts[2]
                target[key]=parts[3]; archived[key]=parts[4]
            }
            close(routes)
            RS=(deb822=="sources" ? "" : "\n")
            ORS=(deb822=="sources" ? "\n\n" : "\n")
        }
        {
            if (deb822=="sources") {
                enabled=tolower(field($0,"Enabled"))
                if (enabled ~ /^no[[:space:]]*$/) { if (mode=="rewrite") print; next }
                nuri=split(field($0,"URIs"),uris,/[[:space:]]+/)
                nsuite=split(field($0,"Suites"),suites,/[[:space:]]+/)
                recognized=0
                for (u=1;u<=nuri;u++) if (kind(uris[u])!="") recognized=1
                if (!recognized) { if (mode=="rewrite") print; next }
                for (u=1;u<=nuri;u++) for (s=1;s<=nsuite;s++) {
                    repo=kind(uris[u]); suite=suites[s]; if (suite=="") continue
                    key=repo "|" suite
                    if (mode=="report") { if (repo!="") printf "%s\t%s\n",repo,suite; continue }
                    if (repo!="" && !(key in target)) exit 1
                    block=replace_field(replace_field($0,"URIs",repo=="" ? uris[u] : target[key]),"Suites",suite)
                    if (repo!="" && target[key]=="SKIP") {
                        block=replace_field(block,"URIs",uris[u]); block=replace_field(block,"Enabled","no")
                        print "# 仓库已不存在，已停用：" suite "\n" block; continue
                    }
                    if (repo!="" && archived[key]==1) block=replace_field(block,"Check-Valid-Until","no")
                    if (distro=="ubuntu" && repo!="" && field(block,"Components") !~ /(^|[[:space:]])universe([[:space:]]|$)/)
                        block=replace_field(block,"Components",field(block,"Components") " universe")
                    print block
                }
            } else {
                n=split($0,words,/[[:space:]]+/); first=1
                if (words[first]=="") first++
                if (words[first]!="deb" && words[first]!="deb-src") { if (mode=="rewrite") print; next }
                uri=first+1
                if (words[uri] ~ /^\[/) { while (uri<=n && words[uri] !~ /\]$/) uri++; uri++ }
                repo=kind(words[uri]); suite=words[uri+1]
                if (repo=="" || suite=="") { if (mode=="rewrite") print; next }
                if (mode=="report") { printf "%s\t%s\n",repo,suite; next }
                key=repo "|" suite
                if (!(key in target)) exit 1
                if (target[key]=="SKIP") { print "# 仓库已不存在，已停用：" $0; next }
                line=words[first]
                for (i=first+1;i<uri;i++) line=line " " words[i]
                if (archived[key]==1) {
                    if (line ~ /check-valid-until=[^] ]+/) gsub(/check-valid-until=[^] ]+/,"check-valid-until=no",line)
                    else if (line ~ /\]$/) sub(/\]$/," check-valid-until=no]",line)
                    else line=line " [check-valid-until=no]"
                }
                line=line " " target[key]
                universe=0
                for (i=uri+2;i<=n;i++) {
                    if (words[i] ~ /^#/) break
                    if (words[i]=="universe") universe=1
                }
                for (i=uri+1;i<=n;i++) {
                    if (distro=="ubuntu" && !universe && words[i] ~ /^#/) { line=line " universe"; universe=1 }
                    line=line " " words[i]
                }
                if (distro=="ubuntu" && !universe) line=line " universe"
                print line
            }
        }
    ' "$2"
}

# 检查 $1 仓库的 $2 suite：Release 存在返回 0，404/410 返回 1，网络或内容异常明确报错。
apt_release_available() {
    local status origin=Debian
    [ "$INSTALL_OS" != ubuntu ] || origin=Ubuntu
    status=$(curl -sSL --retry 2 --connect-timeout 20 --max-time 60 -o "$3" -w '%{http_code}' "$1/dists/$2/Release") ||
        install_error "检查 $origin 仓库失败：$1/dists/$2/Release，请检查网络"
    case "$status" in
        200)
            grep -q "^Origin: $origin" "$3" || install_error "$origin 仓库返回了无效的 Release 文件：$1/dists/$2/Release"
            if [ "$INSTALL_OS" = ubuntu ]; then
                grep -Fxq "Suite: $2" "$3" || install_error "Ubuntu 仓库版本代号不匹配，未切换软件源：$1/dists/$2/Release"
                grep '^Architectures:' "$3" | grep -Eq "(^|[[:space:]])$INSTALL_UBUNTU_ARCH([[:space:]]|$)" ||
                    install_error "Ubuntu 仓库 $2 不提供 $INSTALL_UBUNTU_ARCH 架构，未切换软件源"
            fi
            ;;
        404|410) return 1 ;;
        *) install_error "检查 $origin 仓库失败：HTTP $status，$1/dists/$2/Release" ;;
    esac
}

# 按 suite/架构选择 Debian 或 Ubuntu 的正常/归档源；全部验证和生成成功后备份并写入。
configure_apt_mirror() (
    [ "$INSTALL_OS" = debian ] || [ "$INSTALL_OS" = ubuntu ] || return 0
    require_install_root
    local distro_name=Debian
    if [ "$INSTALL_OS" = ubuntu ]; then
        distro_name=Ubuntu
        INSTALL_UBUNTU_ARCH=$(dpkg --print-architecture) || install_error '无法检测 Ubuntu 软件包架构，未切换软件源'
        [[ "$INSTALL_UBUNTU_ARCH" =~ ^[a-z0-9]+$ ]] || install_error "Ubuntu 软件包架构无效：$INSTALL_UBUNTU_ARCH"
        case "$INSTALL_UBUNTU_ARCH" in amd64|i386) INSTALL_UBUNTU_REPO=main ;; *) INSTALL_UBUNTU_REPO=ports ;; esac
        echo "[信息] Ubuntu 软件包架构：$INSTALL_UBUNTU_ARCH，将为官方源补齐 universe 组件"
    fi
    ensure_install_curl
    local backup_dir="/etc/apt.backup.$(date +%Y%m%d%H%M%S).$$" source_file temp_dir repo suite uri archive_uri
    local -a source_files=()
    temp_dir=$(mktemp -d) || install_error "无法创建 $distro_name 软件源检查临时目录"
    trap 'rm -f -- "$temp_dir"/*; rmdir -- "$temp_dir"' EXIT
    : > "$temp_dir/requests"
    for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
        install_as_root test -f "$source_file" || continue
        source_files+=("$source_file")
        process_apt_sources report "$source_file" '' >> "$temp_dir/requests" || install_error "读取 $distro_name 软件源失败：$source_file"
    done
    sort -u "$temp_dir/requests" > "$temp_dir/suites" || install_error "整理 $distro_name 仓库列表失败"
    [ -s "$temp_dir/suites" ] || install_error "未找到可识别的 $distro_name 官方软件源，请检查 APT 配置"
    : > "$temp_dir/routes"
    while IFS=$'\t' read -r repo suite; do
        [[ "$suite" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]*$ && "$suite" != *..* ]] || install_error "$distro_name 仓库版本代号无效：$suite"
        uri=https://mirrors.tuna.tsinghua.edu.cn/debian
        [ "$repo" != security ] || uri=https://mirrors.tuna.tsinghua.edu.cn/debian-security
        if [ "$INSTALL_OS" = ubuntu ]; then
            uri=https://mirrors.tuna.tsinghua.edu.cn/ubuntu
            [ "$repo" != ports ] || uri=https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports
        fi
        if apt_release_available "$uri" "$suite" "$temp_dir/release"; then
            printf '%s\t%s\t%s\t0\n' "$repo" "$suite" "$uri" >> "$temp_dir/routes"
            echo "[信息] $distro_name 仓库 $suite 使用清华镜像：$uri"
            continue
        fi
        archive_uri=https://mirrors.aliyun.com/debian-archive/debian
        [ "$repo" != security ] || archive_uri=https://mirrors.aliyun.com/debian-archive/debian-security
        [ "$INSTALL_OS" != ubuntu ] || archive_uri=https://mirrors.ustc.edu.cn/ubuntu-old-releases/ubuntu
        if apt_release_available "$archive_uri" "$suite" "$temp_dir/release"; then
            printf '%s\t%s\t%s\t1\n' "$repo" "$suite" "$archive_uri" >> "$temp_dir/routes"
            echo "[信息] $distro_name 仓库 $suite 使用归档镜像：$archive_uri"
        elif { [ "$repo" = main ] || [ "$INSTALL_OS" = ubuntu ]; } && [[ "$suite" =~ -(updates|proposed|proposed-updates|backports|backports-sloppy)$ ]]; then
            printf '%s\t%s\tSKIP\t0\n' "$repo" "$suite" >> "$temp_dir/routes"
            echo "[提示] $distro_name 附加仓库 $suite 在正常源和归档源中均不存在，将停用该条目"
        else
            install_error "$distro_name 仓库 $suite 在正常源和归档源中均不存在，未切换软件源"
        fi
    done < "$temp_dir/suites"
    local index=0
    for source_file in "${source_files[@]}"; do
        process_apt_sources rewrite "$source_file" "$temp_dir/routes" > "$temp_dir/$index" || install_error "生成 $distro_name 软件源失败：$source_file"
        index=$((index+1))
    done
    install_as_root cp -a -- /etc/apt "$backup_dir" || install_error '备份 APT 配置失败，未切换软件源'
    echo "[信息] APT 配置已备份：$backup_dir"
    for ((index=0; index<${#source_files[@]}; index++)); do
        install_as_root cp -- "$temp_dir/$index" "${source_files[index]}" || install_error "写入 $distro_name 软件源失败：${source_files[index]}，原配置备份于 $backup_dir"
    done
)

# 按清华官方模板生成 Stream 9/10 的仓库地址表；$1 输出文件，原配置中的启用和签名字段保留。
generate_centos_stream_template() {
    awk -v version="$INSTALL_OS_VERSION" '
        function emit(id, url) { printf "[%s]\nbaseurl=%s\n\n",id,url }
        BEGIN {
            mirror="https://mirrors.tuna.tsinghua.edu.cn/centos-stream"
            n=split("BaseOS AppStream CRB HighAvailability NFV RT ResilientStorage Devel",repos," ")
            for (i=1;i<=n;i++) {
                id=tolower(repos[i]); url=mirror "/" version "-stream/" repos[i]
                emit(id,url "/$basearch/os")
                emit(id "-debuginfo",url "/$basearch/debug/tree/")
                emit(id "-source",url "/source/tree/")
            }
            url=mirror "/SIGs/" version "-stream/extras/"
            emit("extras-common",url "$basearch/extras-common")
            emit("extras-common-source",url "source/extras-common")
        }
    ' > "$1"
}

# 解析或改写 Stream 原有仓库；$1 模式，$2 repo 文件，$3 主版本，$4 对应版本的 repo 地址表。
process_centos_stream_repos() {
    install_as_root awk -v mode="$1" -v version="$3" -v template="$4" '
        BEGIN {
            if (template!="") {
                while ((getline line < template)>0) {
                    sub(/\r$/, "", line)
                    if (line ~ /^\[/) { id=tolower(line); gsub(/^\[|\]$/, "", id) }
                    else if (line ~ /^[[:space:]]*baseurl[[:space:]]*=/) {
                        sub(/^[^=]*=[[:space:]]*/, "", line); urls[id]=line
                    }
                }
                close(template)
            }
        }
        function emit(    lines,n,i,id,repo,enabled,official,custom,line,value,url,written,continuation) {
            if (block=="") return
            n=split(block,lines,"\n"); id=tolower(lines[1]); gsub(/^[[:space:]]*\[|\][[:space:]]*$/, "", id)
            enabled=1
            for (i=2;i<=n;i++) {
                line=lines[i]; sub(/^[[:space:]]*/,"",line)
                if (line ~ /^enabled[[:space:]]*=/) { value=line; sub(/^[^=]*=[[:space:]]*/,"",value); enabled=(value!=0) }
                if (line ~ /^#?[[:space:]]*(baseurl|mirrorlist|metalink)[[:space:]]*=/) {
                    if (line ~ /\/\/([[:alnum:].-]+\.)?centos\.org\// ||
                        line ~ /\/\/mirrors\.(aliyun\.com|tuna\.tsinghua\.edu\.cn|huaweicloud\.com)\/centos(-stream|-vault|-debuginfo)?\//) official=1
                    else if (line ~ /^baseurl[[:space:]]*=/) custom=1
                }
            }
            if (!official || custom) { if (mode=="rewrite") printf "%s",block; block=""; return }
            url=urls[id]
            if (url=="") {
                repo=id
                if (version==8) {
                    sub(/^highavailability/,"ha",repo)
                    if (repo ~ /-(debug|debuginfo)$/) repo="debuginfo"
                } else {
                    if (repo=="ha" || repo ~ /^ha-/) sub(/^ha/,"highavailability",repo)
                    sub(/-debug$/,"-debuginfo",repo)
                }
                url=urls[repo]
            }
            if (url=="") {
                if (enabled) { print "无法识别已启用的 CentOS Stream 官方仓库：" id > "/dev/stderr"; exit 1 }
                if (mode=="rewrite") printf "%s",block
                block=""; return
            }
            if (mode=="report") { if (enabled) printf "%s\t%s\n",id,url }
            else for (i=1;i<=n;i++) {
                line=lines[i]
                if (continuation && line ~ /^[[:space:]]+(https?|ftp|file):\/\//) line="# " line
                else {
                    continuation=0
                    if (line ~ /^[[:space:]]*#?[[:space:]]*baseurl[[:space:]]*=/ && !written) { line="baseurl=" url; written=1; continuation=1 }
                    else if (line ~ /^[[:space:]]*(baseurl|mirrorlist|metalink)[[:space:]]*=/) { line="# " line; continuation=1 }
                }
                if (i<n || line!="") print line
            }
            if (mode=="rewrite" && !written) print "baseurl=" url
            block=""
        }
        /^[[:space:]]*\[/ { emit() }
        { sub(/\r$/, ""); block=block $0 "\n" }
        END { emit() }
    ' "$2"
}

# Stream 8 下载阿里云归档 repo，9/10 按清华模板生成；索引验证成功后才备份并写入。
configure_centos_stream_mirror() (
    local source_file temp_dir repo uri basearch template mirror_name index=0
    local backup_dir="/etc/yum.repos.d.backup.$(date +%Y%m%d%H%M%S).$$"
    local -a source_files=()
    case "$INSTALL_OS_VERSION" in
        8) mirror_name=阿里云归档 ;;
        9|10) mirror_name=清华 ;;
        *) install_error "当前 CentOS Stream $INSTALL_OS_VERSION 暂无已验证的自动换源配置" ;;
    esac
    ensure_install_curl
    basearch=$(uname -m)
    case "$basearch" in x86_64|aarch64|ppc64le|s390x) ;; *) install_error "CentOS Stream 架构暂不支持自动换源：$basearch" ;; esac
    temp_dir=$(mktemp -d) || install_error '无法创建 CentOS Stream 换源临时目录'
    trap 'rm -f -- "$temp_dir"/*; rmdir -- "$temp_dir"' EXIT
    template="$temp_dir/templates"
    if [ "$INSTALL_OS_VERSION" = 8 ]; then
        : > "$template"
        echo '[信息] 正在下载 CentOS Stream 8 阿里云专用 repo 文件…'
        for repo in BaseOS AppStream Extras Extras-common PowerTools HighAvailability ResilientStorage NFV RealTime Debuginfo Sources Media; do
            uri="http://mirrors.aliyun.com/repo/centos-stream/8/CentOS-Stream-$repo.repo"
            download_install_file "$uri" "$temp_dir/download.repo" || install_error "下载 CentOS Stream 8 repo 失败，未修改软件源：$uri"
            grep -q '^\[[^]]\+\]' "$temp_dir/download.repo" && grep -q '^[[:space:]]*baseurl[[:space:]]*=' "$temp_dir/download.repo" ||
                install_error "下载的 CentOS Stream 8 repo 无效，未修改软件源：$uri"
            cat "$temp_dir/download.repo" >> "$template"
            printf '\n' >> "$template"
        done
    else
        echo "[信息] 正在按清华官方模板生成 CentOS Stream $INSTALL_OS_VERSION 软件源配置…"
        generate_centos_stream_template "$template" || install_error '生成 CentOS Stream 清华软件源模板失败，未修改软件源'
    fi
    : > "$temp_dir/repos"
    for source_file in /etc/yum.repos.d/*.repo; do
        install_as_root test -f "$source_file" || continue
        source_files+=("$source_file")
        process_centos_stream_repos report "$source_file" "$INSTALL_OS_VERSION" "$template" >> "$temp_dir/repos" || install_error "读取 CentOS Stream 仓库失败：$source_file"
        process_centos_stream_repos rewrite "$source_file" "$INSTALL_OS_VERSION" "$template" > "$temp_dir/$index.repo" || install_error "生成 CentOS Stream 仓库失败：$source_file"
        index=$((index+1))
    done
    [ -s "$temp_dir/repos" ] || install_error '未找到可切换的 CentOS Stream 官方仓库，请检查现有 repo 配置'
    echo "[信息] 正在检查 CentOS Stream $INSTALL_OS_VERSION $mirror_name 镜像…"
    while IFS=$'\t' read -r repo uri; do
        uri=${uri//\$basearch/$basearch}
        uri=${uri//\$stream/$INSTALL_OS_VERSION-stream}
        uri=${uri//\$contentdir/centos}
        uri=${uri//\$releasever/$INSTALL_OS_VERSION}
        download_install_file "${uri%/}/repodata/repomd.xml" "$temp_dir/repomd.xml" || install_error "CentOS Stream 仓库 $repo 不可访问，未修改软件源：$uri"
        grep -q '<repomd[ >]' "$temp_dir/repomd.xml" || install_error "CentOS Stream 仓库 $repo 返回了无效索引，未修改软件源"
    done < "$temp_dir/repos"
    install_as_root cp -a -- /etc/yum.repos.d "$backup_dir" || install_error '备份 CentOS Stream 软件源失败，未修改配置'
    echo "[信息] CentOS Stream 软件源已备份：$backup_dir"
    for ((index=0; index<${#source_files[@]}; index++)); do
        if ! install_as_root cmp -s "$temp_dir/$index.repo" "${source_files[index]}"; then
            install_as_root cp -- "$temp_dir/$index.repo" "${source_files[index]}" || install_error "写入 CentOS Stream 软件源失败，原配置备份于 $backup_dir"
        fi
    done
)

# CentOS Linux 使用用户提供的阿里云 repo 文件；Linux 8 仍分别下载两份相同内容。
configure_centos_linux_mirror() {
    [ "$INSTALL_OS" = centos ] || return 0
    require_install_root
    local repo_url source_file index
    local -a repo_targets=() download_files=()
    local backup_suffix="$(date +%Y%m%d%H%M%S).$$" repo_dir=/etc/yum.repos.d
    case "$INSTALL_OS_VERSION" in
        7) repo_url=http://mirrors.aliyun.com/repo/Centos-7.repo; repo_targets=("$repo_dir/CentOS-Base.repo") ;;
        8) repo_url=http://mirrors.aliyun.com/repo/Centos-8.repo; repo_targets=("$repo_dir/CentOS-Linux-BaseOS.repo" "$repo_dir/CentOS-Linux-AppStream.repo") ;;
        *) install_error "自动换源仅支持 CentOS Linux 7/8，当前版本为 $INSTALL_OS_VERSION" ;;
    esac
    echo "[信息] 正在下载 CentOS $INSTALL_OS_VERSION 阿里云软件源…"
    for ((index=0; index<${#repo_targets[@]}; index++)); do
        download_files[index]=$(mktemp) ||
            { rm -f -- "${download_files[@]}"; install_error '无法创建 CentOS 软件源下载临时文件'; }
        download_install_file "$repo_url" "${download_files[index]}" ||
            { rm -f -- "${download_files[@]}"; install_error "下载 CentOS 阿里云软件源失败：${repo_targets[index]}，未切换软件源"; }
        if ! grep -q '^\[base\]' "${download_files[index]}" || \
            { [ "$INSTALL_OS_VERSION" = 8 ] && ! grep -q '^\[AppStream\]' "${download_files[index]}"; }; then
            rm -f -- "${download_files[@]}"
            install_error '下载的 CentOS 软件源缺少 BaseOS 或 AppStream 配置，未切换软件源'
        fi
    done
    install_as_root cp -a -- "$repo_dir" "$repo_dir.backup.$backup_suffix" ||
        { rm -f -- "${download_files[@]}"; install_error '备份 YUM 配置失败，未切换软件源'; }
    echo "[信息] YUM 配置已备份：$repo_dir.backup.$backup_suffix"
    for source_file in "$repo_dir"/CentOS-*.repo; do
        install_as_root test -f "$source_file" || continue
        install_as_root mv -- "$source_file" "$source_file.backup.$backup_suffix" ||
            { rm -f -- "${download_files[@]}"; install_error "备份旧 CentOS 软件源失败：$source_file"; }
    done
    for ((index=0; index<${#repo_targets[@]}; index++)); do
        install_as_root install -m 0644 "${download_files[index]}" "${repo_targets[index]}" ||
            { rm -f -- "${download_files[@]}"; install_error "写入 CentOS 阿里云软件源失败，原配置备份于 $repo_dir.backup.$backup_suffix"; }
    done
    rm -f -- "${download_files[@]}"
}

# 按 CentOS Linux/Stream 选择对应源，随后统一清理缓存、生成缓存并更新软件包。
configure_centos_mirror() {
    [ "$INSTALL_OS" = centos ] || return 0
    require_install_root
    if [[ "$INSTALL_OS_NAME" == *CentOS\ Stream* ]] || grep -qs 'CentOS Stream' /etc/*release*; then
        INSTALL_CENTOS_STREAM=1
        configure_centos_stream_mirror
    else
        INSTALL_CENTOS_STREAM=0
        configure_centos_linux_mirror
    fi
    install_as_root "$INSTALL_PM" clean all || install_error '清理 CentOS 软件包缓存失败'
    install_as_root "$INSTALL_PM" makecache || install_error '刷新 CentOS 软件包缓存失败，请检查对应版本的软件源和网络'
    install_as_root "$INSTALL_PM" update -y || install_error '更新 CentOS 系统软件包失败，请检查软件源和网络'
}

# Debian/Ubuntu 安装软件前刷新索引；任一软件源更新失败立即停止，同次部署只刷新一次。
update_install_index() {
    if { [ "$INSTALL_PM" != apt ] && [ "$INSTALL_PM" != apt-get ]; } || [ "$INSTALL_APT_UPDATED" = 1 ]; then return; fi
    echo '[信息] 正在更新 APT 软件包索引…'
    install_as_root apt-get -o APT::Update::Error-Mode=any update ||
        install_error 'APT 软件包索引更新失败，请检查软件源和网络后重试'
    INSTALL_APT_UPDATED=1
}

# 以安装权限检查配置和符号链接，避免普通账号无读取权限时误判为不存在。
install_path_exists() {
    install_as_root test -e "$1" || install_as_root test -L "$1"
}

# 检查并安装下载工具；只补齐 curl，不触发软件源切换。
ensure_install_curl() {
    if ! command -v curl >/dev/null 2>&1; then
        require_install_root
        detect_install_os
        update_install_index
        echo '[信息] curl 未安装，开始自动安装下载工具…'
        install_as_root "$INSTALL_PM" install -y curl || install_error '安装 curl 下载工具失败'
    fi
}

# 统一用 curl 将地址 $1 下载到文件 $2；自动补齐 curl，返回下载状态并保留错误输出。
download_install_file() {
    ensure_install_curl
    curl -fsSL --retry 3 --connect-timeout 30 --max-time 120 -o "$2" "$1" </dev/null
}

# 读取系统名称和完整版本；主版本供换源使用，此处不限制可部署的发行版。
read_install_os_info() {
    local ID='' VERSION_ID='' PRETTY_NAME='' NAME='' DISTRIB_ID='' DISTRIB_RELEASE='' DISTRIB_DESCRIPTION=''
    if [ -r /etc/os-release ]; then
        . /etc/os-release
    elif [ -r /usr/lib/os-release ]; then
        . /usr/lib/os-release
    elif [ -r /etc/lsb-release ]; then
        . /etc/lsb-release
        if [ "$DISTRIB_ID" = Ubuntu ]; then
            ID=ubuntu; VERSION_ID="$DISTRIB_RELEASE"; PRETTY_NAME="$DISTRIB_DESCRIPTION"; NAME=Ubuntu
        fi
    elif [ -r /etc/debian_version ]; then
        ID=debian
        NAME='Debian GNU/Linux'
        VERSION_ID=$(cat /etc/debian_version)
    fi
    INSTALL_OS="$ID"
    INSTALL_OS_VERSION="${VERSION_ID%%.*}"
    INSTALL_OS_FULL_VERSION="$VERSION_ID"
    INSTALL_OS_NAME="${PRETTY_NAME:-${NAME:-${ID:-Linux（缺少发行版信息）}}}"
}

# 仅缺少组件时检查自动安装支持范围；已有可用 Docker/Compose 的环境不受限制。
detect_install_os() {
    read_install_os_info
    [ -n "$INSTALL_OS" ] || install_error '无法识别 Linux 发行版：缺少系统版本信息'
    case "$INSTALL_OS" in
        ubuntu|debian) INSTALL_PM=apt; command -v apt >/dev/null 2>&1 || INSTALL_PM=apt-get ;;
        centos) INSTALL_PM=yum; command -v yum >/dev/null 2>&1 || INSTALL_PM=dnf ;;
        *) install_error "自动安装暂不支持 $INSTALL_OS，请手动安装 Docker 与 Compose 后重试" ;;
    esac
    command -v "$INSTALL_PM" >/dev/null 2>&1 || install_error "缺少包管理器 $INSTALL_PM"
}

# 直接采用 build-env1.sh 的 Docker 包、阿里云源和 daemon.json 下载地址。
install_docker() {
    # 软件源切换仅在 Docker 命令不存在时执行，已安装的环境及其软件源保持原样。
    if type -P docker >/dev/null 2>&1; then return; fi
    require_install_root
    detect_install_os
    echo '[信息] Docker 未安装，开始自动安装…'
    configure_apt_mirror
    configure_centos_mirror
    if [ "$INSTALL_PM" = apt ] || [ "$INSTALL_PM" = apt-get ]; then
        update_install_index
        install_as_root env DEBIAN_FRONTEND=noninteractive "$INSTALL_PM" install -y docker.io || install_error 'Docker 安装失败，请检查该系统版本是否提供可用的 docker.io 软件包'
    else
        if [ "$INSTALL_CENTOS_STREAM" = 1 ]; then
            install_as_root "$INSTALL_PM" install -y dnf-plugins-core device-mapper-persistent-data lvm2 || install_error '安装 CentOS Stream Docker 软件源依赖失败'
        else
            install_as_root yum install -y yum-utils device-mapper-persistent-data lvm2 || install_error '安装 Docker 软件源依赖失败'
        fi
        if install_path_exists /etc/yum.repos.d/docker-ce.repo; then
            install_as_root cp -a -- /etc/yum.repos.d/docker-ce.repo "/etc/yum.repos.d/docker-ce.repo.backup.$(date +%Y%m%d%H%M%S).$$" ||
                install_error '备份已有 Docker 软件源失败'
        fi
        if [ "$INSTALL_CENTOS_STREAM" = 1 ]; then
            local docker_repo
            docker_repo=$(mktemp) || install_error '无法创建 Docker CE 软件源下载临时文件'
            download_install_file 'http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo' "$docker_repo" ||
                { rm -f -- "$docker_repo"; install_error '下载阿里云 Docker CE 软件源失败'; }
            grep -q '^\[docker-ce-stable\]' "$docker_repo" ||
                { rm -f -- "$docker_repo"; install_error '下载的 Docker CE 软件源无效'; }
            install_as_root install -m 0644 "$docker_repo" /etc/yum.repos.d/docker-ce.repo ||
                { rm -f -- "$docker_repo"; install_error '写入阿里云 Docker CE 软件源失败'; }
            rm -f -- "$docker_repo"
        else
            install_as_root yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo || install_error '添加阿里云 Docker CE 软件源失败'
        fi
        install_as_root "$INSTALL_PM" install -y docker-ce docker-ce-cli containerd.io || install_error 'Docker CE 安装失败'
        install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
        install_as_root systemctl start docker || install_error 'Docker 启动失败'
    fi
    type -P docker >/dev/null 2>&1 || install_error '安装完成后仍未找到 Docker 命令'
    # 下载参考脚本使用的配置；已有配置保留，避免覆盖服务器原有设置。
    if ! install_path_exists /etc/docker/daemon.json; then
        local config_file
        config_file=$(mktemp) || install_error '无法创建 Docker 配置临时文件'
        download_install_file 'https://selfdownload.zhinianboke.com/file/website/docker/daemon.json' "$config_file" ||
            { rm -f -- "$config_file"; install_error '下载 Docker 配置失败'; }
        install_as_root mkdir -p /etc/docker ||
            { rm -f -- "$config_file"; install_error '创建 Docker 配置目录失败'; }
        install_as_root install -m 0644 "$config_file" /etc/docker/daemon.json ||
            { rm -f -- "$config_file"; install_error '写入 Docker 配置失败'; }
        rm -f -- "$config_file"
        install_as_root systemctl restart docker.service || install_error '应用 Docker 配置并重启失败'
    fi
}

# 所有部署阶段的 Docker 调用使用同一权限；command 避免同名函数递归。
docker() {
    command "${DOCKER_PREFIX[@]}" docker "$@"
}

# 优先使用插件，也兼容已有可执行的 docker-compose 独立命令。
select_compose() {
    if docker compose version >/dev/null 2>&1; then
        DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }docker compose"
    elif command "${DOCKER_PREFIX[@]}" docker-compose version >/dev/null 2>&1; then
        DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }docker-compose"
    else
        return 1
    fi
}

# 采用 build-env1.sh 的 docker-compose 文件、安装位置和软链接。
install_compose() {
    require_install_root
    local compose_file target=/usr/local/bin/docker-compose link=/usr/bin/docker-compose
    echo '[信息] docker-compose 未安装，开始从参考脚本地址下载安装…'
    compose_file=$(mktemp) || install_error '无法创建 docker-compose 下载临时文件'
    download_install_file 'https://selfdownload.zhinianboke.com/file/website/docker/docker-compose' "$compose_file" ||
        { rm -f -- "$compose_file"; install_error 'docker-compose 下载失败'; }
    install_as_root mkdir -p /usr/local/bin ||
        { rm -f -- "$compose_file"; install_error '创建 docker-compose 安装目录失败'; }
    if install_path_exists "$target"; then
        install_as_root cp -a -- "$target" "$target.backup.$(date +%Y%m%d%H%M%S).$$" ||
            { rm -f -- "$compose_file"; install_error '备份已有 docker-compose 文件失败'; }
    fi
    install_as_root install -m 0755 "$compose_file" "$target" ||
        { rm -f -- "$compose_file"; install_error '安装 docker-compose 文件失败'; }
    rm -f -- "$compose_file"
    if install_path_exists "$link" && [ "$(install_as_root readlink "$link" || true)" != "$target" ]; then
        install_as_root mv -- "$link" "$link.backup.$(date +%Y%m%d%H%M%S).$$" ||
            install_error '备份已有 docker-compose 链接失败'
    fi
    if ! install_path_exists "$link"; then
        install_as_root ln -s "$target" "$link" || install_error '创建 docker-compose 软链接失败'
    fi
    command "${DOCKER_PREFIX[@]}" "$target" --version ||
        install_error '下载的 docker-compose 无法运行，请检查服务器架构及运行依赖'
    # 使用完整路径，避免 SSH 账号 PATH 未包含 /usr/local/bin。
    DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }$target"
}

prepare_docker_environment() {
    [ "$(uname -s)" = Linux ] || install_error '此部署脚本仅支持 Linux 服务器'
    local installed=0 context=''
    read_install_os_info
    printf '[信息] 检测到系统：%s\n' "$INSTALL_OS_NAME"
    printf '[信息] 系统版本：%s（发行版：%s）\n' "${INSTALL_OS_FULL_VERSION:-未提供}" "${INSTALL_OS:-未识别}"
    printf '[信息] 系统架构：%s\n' "$(uname -m)"
    # 函数 docker 已定义，使用 type -P 检查真实客户端，避免把函数误当已安装。
    if ! type -P docker >/dev/null 2>&1; then install_docker; installed=1; fi
    docker --version || install_error 'Docker 客户端无法执行，请检查安装或 CPU 架构'
    if ! docker info >/dev/null 2>&1; then
        context=$(docker context show 2>/dev/null || true)
        if [ -n "${DOCKER_HOST:-}" ] || [ -n "${DOCKER_CONTEXT:-}" ] || { [ -n "$context" ] && [ "$context" != default ]; }; then
            docker info || true
            install_error '当前 Docker 自定义/远程连接不可用，请检查连接配置和权限'
        fi
        require_install_root
        DOCKER_PREFIX=("${INSTALL_ROOT[@]}")
        if ! docker info >/dev/null 2>&1; then
            if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
                install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
                install_as_root systemctl start docker || install_error 'Docker 启动失败，请检查服务日志和 daemon.json'
            elif command -v service >/dev/null 2>&1; then
                install_as_root service docker start || install_error 'Docker 服务启动失败'
            else
                install_error '没有可用的服务管理器，请手动启动 Docker 后重试'
            fi
        fi
    fi
    if [ "$installed" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
    fi
    local attempt
    for ((attempt=1; attempt<=30; attempt++)); do
        if docker info >/dev/null 2>&1; then break; fi
        sleep 1
    done
    docker info >/dev/null || install_error 'Docker 守护进程不可用，请检查服务日志和访问权限'
    if select_compose; then return; fi
    install_compose
}

prepare_docker_environment </dev/null

export COMPOSE_PROJECT_NAME=xianyu-auto-reply
# 数组保留路径中的空格；日志中的命令使用 Shell 转义，方便直接复制执行。
read -r -a COMPOSE_COMMAND <<< "$DC"
COMPOSE_COMMAND+=(-f "$COMPOSE_FILE" --env-file "$ENV_FILE")
printf -v DC_CMD '%q ' "${COMPOSE_COMMAND[@]}"
DC_CMD=${DC_CMD% }

echo -e "${CYAN}[信息] Docker: $(docker --version)${NC}"
echo -e "${CYAN}[信息] Compose: $DC${NC}"
echo -e "${CYAN}[信息] 项目目录: $WORK_DIR${NC}"
echo ""

# ========== 生成 .env 配置文件 ==========
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[提示] 首次部署，生成默认配置文件 .env${NC}"
    cat > "$ENV_FILE" << 'ENVEOF'
# ==========================================
# 闲鱼自动回复系统 - 环境变量配置
# ==========================================

# MySQL数据库配置（Docker内置，自动创建）
MYSQL_ROOT_PASSWORD=xianyu@2026
MYSQL_DATABASE=xianyu_data
MYSQL_USER=xianyu
MYSQL_PASSWORD=xianyu@2026
MYSQL_MAX_CONNECTIONS=4000

# 数据库连接池配置（三个服务峰值合计 2640，低于 MySQL 最大连接数并预留管理连接）
BACKEND_DB_POOL_SIZE=800
BACKEND_DB_MAX_OVERFLOW=60
WEBSOCKET_DB_POOL_SIZE=800
WEBSOCKET_DB_MAX_OVERFLOW=150
SCHEDULER_DB_POOL_SIZE=800
SCHEDULER_DB_MAX_OVERFLOW=30
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
DB_POOL_USE_LIFO=true
DB_CONNECT_TIMEOUT=10

# Redis缓存配置（Docker内置）
REDIS_PASSWORD=xianyu@2026
REDIS_DB=0
REDIS_POOL_SIZE=800
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=3
REDIS_SOCKET_KEEPALIVE=true
REDIS_SOCKET_KEEPALIVE_IDLE=60
REDIS_SOCKET_KEEPALIVE_INTERVAL=10
REDIS_SOCKET_KEEPALIVE_COUNT=3
REDIS_HEALTH_CHECK_INTERVAL=30
REDIS_PROTOCOL=2
REDIS_STARTUP_MAX_RETRIES=5
REDIS_STARTUP_RETRY_BASE_DELAY=1
REDIS_STARTUP_RETRY_CAP_DELAY=10

# 说明：JWT 密钥由数据库统一托管（首次启动自动生成并持久化），无需在此配置

# 端口配置
FRONTEND_PORT=9000
BACKEND_WEB_PORT=8089
WEBSOCKET_PORT=8090
SCHEDULER_PORT=8091

# 镜像配置
IMAGE_REGISTRY=registry.cn-shanghai.aliyuncs.com/zhinian-software
IMAGE_TAG=latest

# 基础镜像（MySQL / Redis，从阿里云仓库拉取，由 sync_base_images.sh 同步上传）
MYSQL_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-mysql:8.0
REDIS_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-redis:7-alpine

# 日志级别
LOG_LEVEL=INFO

# 在线安装：SSH 连接超时、脚本执行上限和任务日志保留期（秒）
ONLINE_INSTALL_CONNECT_TIMEOUT=60
ONLINE_INSTALL_TIMEOUT=7200
ONLINE_INSTALL_RETENTION_SECONDS=86400

# SQL 日志开关：true=打印每条执行的完整 SQL（便于排查）；默认 false，高并发生产环境建议保持关闭
SQL_ECHO=false

# IM Token 缓存（xy_token_cache 表）随机过期时间区间（小时），不配置默认 5~10 小时
TOKEN_CACHE_TTL_MIN_HOURS=5
TOKEN_CACHE_TTL_MAX_HOURS=10

# Token过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_MINUTES=10080

# 定时任务间隔（分钟）
REDELIVERY_INTERVAL=5
RATE_INTERVAL=20

# 验证码并发数
MAX_CAPTCHA_CONCURRENT=3

# WebSocket 启动时是否自动连接账号
AUTO_START_WEBSOCKET=true
# 滑块验证 DrissionPage 兜底引擎（主引擎失败后重试）：开关 / 超时秒 / 无头
CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=false
CAPTCHA_DRISSIONPAGE_TIMEOUT=25
CAPTCHA_DRISSIONPAGE_HEADLESS=true

# 分销卡券上游服务基址（「分销卡券」页面提货 + 个人设置一键创建对接卡密秘钥共用此基址）
CARD_DOCK_BASE_URL=http://backend.zhinianboke.com
# 个人设置「对接卡密秘钥」一键创建密钥的鉴权 key（基址复用 CARD_DOCK_BASE_URL）
EXTERNAL_API_KEY=zhinian_bk

# 前端公网访问地址（用于生成前端页面分享链接，留空则使用默认）
FRONTEND_PUBLIC_URL=
# 启动时是否自动启动 Goofish 定时采集任务
AUTO_START_CRAWL_JOBS=true
# 远程官方服务基址（仪表盘广告、系统公告 = 本地内容 + 远程官方内容）
REMOTE_OFFICIAL_BASE_URL=https://xy.zhinianboke.com
# 是否启用远程官方广告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_ADS=true
# 是否启用远程官方公告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_ANNOUNCEMENTS=true
# 是否启用远程官方弹窗公告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_POPUP_ANNOUNCEMENTS=true
ENVEOF
    echo -e "${GREEN}✓ 已生成 .env 文件${NC}"
    echo -e "${YELLOW}[提示] 如需修改配置（如端口等），请编辑 $ENV_FILE 后重新运行${NC}"
    echo ""
fi

# ========== 生成 docker-compose.deploy.yml（远程镜像版） ==========
echo "[信息] 生成 docker-compose.deploy.yml（远程镜像版）..."
cat > "$COMPOSE_FILE" << 'COMPOSEEOF'
# Docker Compose 配置文件 - 远程镜像部署版
# 闲鱼自动回复系统 - 从镜像仓库拉取预构建镜像
# 由 deploy.sh 自动生成，请勿手动修改

services:
  # ====== 基础设施 ======

  # MySQL数据库（默认从阿里云仓库拉取，可通过 MYSQL_IMAGE 覆盖）
  mysql:
    image: ${MYSQL_IMAGE:-registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-mysql:8.0}
    container_name: xianyu-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - TZ=Asia/Shanghai
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max-connections=${MYSQL_MAX_CONNECTIONS:-4000}
      - --max-connect-errors=100000
      - --max-allowed-packet=256M
      - --default-time-zone=+08:00
    volumes:
      - ./xianyu_auto_reply/mysql/data:/var/lib/mysql
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-xianyu@2026}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  # Redis缓存（默认从阿里云仓库拉取，可通过 REDIS_IMAGE 覆盖）
  redis:
    image: ${REDIS_IMAGE:-registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-redis:7-alpine}
    container_name: xianyu-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:-xianyu@2026}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/redis/data:/data
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-xianyu@2026}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ====== 应用服务（远程镜像） ======

  # Backend-Web 服务
  backend-web:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-backend-web:${IMAGE_TAG:-latest}
    container_name: xianyu-backend-web
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${BACKEND_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${BACKEND_DB_MAX_OVERFLOW:-60}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - BACKEND_WEB_PORT=8089
      - ONLINE_INSTALL_CONNECT_TIMEOUT=${ONLINE_INSTALL_CONNECT_TIMEOUT:-60}
      - ONLINE_INSTALL_TIMEOUT=${ONLINE_INSTALL_TIMEOUT:-7200}
      - ONLINE_INSTALL_RETENTION_SECONDS=${ONLINE_INSTALL_RETENTION_SECONDS:-86400}
      - HOST=0.0.0.0
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=${ACCESS_TOKEN_EXPIRE_MINUTES:-1440}
      - REFRESH_TOKEN_EXPIRE_MINUTES=${REFRESH_TOKEN_EXPIRE_MINUTES:-10080}
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - CORS_ORIGINS=*
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - SCHEDULER_SERVICE_URL=http://scheduler:8091
      - FRONTEND_SERVICE_URL=${FRONTEND_SERVICE_URL:-http://frontend:80}
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - BACKEND_WEB_PUBLIC_URL=${BACKEND_WEB_PUBLIC_URL:-}
      - CARD_DOCK_BASE_URL=${CARD_DOCK_BASE_URL:-http://backend.zhinianboke.com}
      - EXTERNAL_API_KEY=${EXTERNAL_API_KEY:-zhinian_bk}
      - FRONTEND_PUBLIC_URL=${FRONTEND_PUBLIC_URL:-}
      - AUTO_START_CRAWL_JOBS=${AUTO_START_CRAWL_JOBS:-true}
      - REMOTE_OFFICIAL_BASE_URL=${REMOTE_OFFICIAL_BASE_URL:-https://xy.zhinianboke.com}
      - ENABLE_REMOTE_ADS=${ENABLE_REMOTE_ADS:-true}
      - ENABLE_REMOTE_ANNOUNCEMENTS=${ENABLE_REMOTE_ANNOUNCEMENTS:-true}
      - ENABLE_REMOTE_POPUP_ANNOUNCEMENTS=${ENABLE_REMOTE_POPUP_ANNOUNCEMENTS:-true}
      - BROWSER_HEADLESS=true
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TOKEN_CACHE_TTL_MIN_HOURS=${TOKEN_CACHE_TTL_MIN_HOURS:-5}
      - TOKEN_CACHE_TTL_MAX_HOURS=${TOKEN_CACHE_TTL_MAX_HOURS:-10}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/backend_web:/app/backend-web/logs
      - ./xianyu_auto_reply/static:/app/static
      - ./xianyu_auto_reply/backups:/app/backups
    ports:
      - "${BACKEND_WEB_PORT:-8089}:8089"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8089/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # WebSocket 服务
  websocket:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-websocket:${IMAGE_TAG:-latest}
    container_name: xianyu-websocket
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${WEBSOCKET_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${WEBSOCKET_DB_MAX_OVERFLOW:-150}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - WEBSOCKET_PORT=8090
      - HOST=0.0.0.0
      - MAX_CAPTCHA_CONCURRENT=${MAX_CAPTCHA_CONCURRENT:-3}
      - BROWSER_HEADLESS=true
      - AUTO_START_WEBSOCKET=${AUTO_START_WEBSOCKET:-true}
      - CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=${CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED:-false}
      - CAPTCHA_DRISSIONPAGE_TIMEOUT=${CAPTCHA_DRISSIONPAGE_TIMEOUT:-25}
      - CAPTCHA_DRISSIONPAGE_HEADLESS=${CAPTCHA_DRISSIONPAGE_HEADLESS:-true}
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - STATIC_DIR=/app/static
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TOKEN_CACHE_TTL_MIN_HOURS=${TOKEN_CACHE_TTL_MIN_HOURS:-5}
      - TOKEN_CACHE_TTL_MAX_HOURS=${TOKEN_CACHE_TTL_MAX_HOURS:-10}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/websocket:/app/websocket/logs
      - ./xianyu_auto_reply/static:/app/static
      - ./xianyu_auto_reply/browser_data:/app/browser_data
    ports:
      - "${WEBSOCKET_PORT:-8090}:8090"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      backend-web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Scheduler 服务
  scheduler:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-scheduler:${IMAGE_TAG:-latest}
    container_name: xianyu-scheduler
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${SCHEDULER_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${SCHEDULER_DB_MAX_OVERFLOW:-30}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - SCHEDULER_PORT=8091
      - HOST=0.0.0.0
      - REDELIVERY_INTERVAL=${REDELIVERY_INTERVAL:-5}
      - RATE_INTERVAL=${RATE_INTERVAL:-20}
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/scheduler:/app/scheduler/logs
      - ./xianyu_auto_reply/static:/app/static:ro
      - ./xianyu_auto_reply/backups:/app/backups
    ports:
      - "${SCHEDULER_PORT:-8091}:8091"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      websocket:
        condition: service_healthy
      backend-web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8091/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # 前端服务
  frontend:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-frontend:${IMAGE_TAG:-latest}
    container_name: xianyu-frontend
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
    ports:
      - "${FRONTEND_PORT:-9000}:80"
    networks:
      - xianyu-network
    depends_on:
      backend-web:
        condition: service_healthy

networks:
  xianyu-network:
    driver: bridge
COMPOSEEOF
echo -e "${GREEN}✓ docker-compose.deploy.yml 已生成${NC}"
echo ""

# 在停止任何旧容器前验证配置，错误直接展示并终止。
"${COMPOSE_COMMAND[@]}" config --quiet || install_error 'Compose 配置验证失败，请检查 .env 和 Docker Compose 版本'

# ========== 检测并清理加密版残留 ==========
ENC_CONTAINERS=(
    "xianyu-enc-frontend"
    "xianyu-enc-backend-web"
    "xianyu-enc-websocket"
    "xianyu-enc-scheduler"
    "xianyu-enc-mysql"
    "xianyu-enc-redis"
)

enc_found=0
container_names=$(docker ps -a --format '{{.Names}}') || install_error '读取现有容器列表失败，已停止部署'
for container in "${ENC_CONTAINERS[@]}"; do
    if printf '%s\n' "$container_names" | grep -Fxq -- "$container"; then
        enc_found=1
        break
    fi
done

if [ $enc_found -eq 1 ]; then
    echo -e "${YELLOW}[信息] 检测到加密版容器，清理中（保留数据卷）...${NC}"
    for container in "${ENC_CONTAINERS[@]}"; do
        if printf '%s\n' "$container_names" | grep -Fxq -- "$container"; then
            echo -e "${CYAN}  停止并删除容器: ${container}${NC}"
            docker stop "$container" || install_error "停止加密版容器 $container 失败，已停止部署"
            docker rm "$container" || install_error "移除加密版容器 $container 失败，已停止部署"
        fi
    done
    # 清理加密版应用镜像
    for name in "xianyu-enc-frontend" "xianyu-enc-backend-web" "xianyu-enc-websocket" "xianyu-enc-scheduler"; do
        image_ids=$(docker images --filter "reference=*/${name}" --format '{{.ID}}') || install_error '读取加密版应用镜像失败'
        image_ids=$(printf '%s\n' "$image_ids" | sort -u)
        for id in $image_ids; do
            docker rmi "$id" || echo "[提示] 加密版镜像 $id 未移除，可能仍被其他容器使用，继续部署"
        done
    done
    # 按 Compose 项目标签清理，避免仅凭名称片段误删其他项目的网络。
    enc_networks=$(docker network ls --filter 'label=com.docker.compose.project=xianyu_auto_reply_enc' --format '{{.Name}}') ||
        install_error '读取加密版项目网络失败'
    for enc_network in $enc_networks; do
        docker network rm "$enc_network" || echo "[提示] 网络 $enc_network 未移除，可能仍在使用，继续部署"
    done
    echo -e "${GREEN}✓ 加密版已清理（数据卷已保留）${NC}"
    echo ""
fi

# ========== 创建挂载目录 ==========
mkdir -p \
    "$WORK_DIR/xianyu_auto_reply/mysql/data" \
    "$WORK_DIR/xianyu_auto_reply/redis/data" \
    "$WORK_DIR/xianyu_auto_reply/logs/backend_web" \
    "$WORK_DIR/xianyu_auto_reply/logs/websocket" \
    "$WORK_DIR/xianyu_auto_reply/logs/scheduler" \
    "$WORK_DIR/xianyu_auto_reply/static" \
    "$WORK_DIR/xianyu_auto_reply/backups" \
    "$WORK_DIR/xianyu_auto_reply/browser_data"

# ========== 部署 ==========
echo -e "${YELLOW}步骤 1/3: 拉取最新镜像（旧容器保持运行，减少停机时间）...${NC}"
"${COMPOSE_COMMAND[@]}" pull
echo -e "${GREEN}✓ 镜像拉取完成${NC}"

echo ""
echo -e "${YELLOW}步骤 2/3: 停止旧容器（仅本项目）...${NC}"
"${COMPOSE_COMMAND[@]}" down || install_error '停止本项目旧容器失败，请检查 Docker 状态后重试'
echo -e "${GREEN}✓ 旧容器已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 3/3: 启动服务...${NC}"
"${COMPOSE_COMMAND[@]}" up -d
echo -e "${GREEN}✓ 服务已启动${NC}"

echo ""
echo "[信息] 等待服务启动..."
sleep 15
"${COMPOSE_COMMAND[@]}" ps

# 读取端口配置
frontend_port=$(grep -E "^FRONTEND_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "9000")
backend_web_port=$(grep -E "^BACKEND_WEB_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8089")
websocket_port=$(grep -E "^WEBSOCKET_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8090")
scheduler_port=$(grep -E "^SCHEDULER_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8091")

frontend_port="${frontend_port:-9000}"
backend_web_port="${backend_web_port:-8089}"
websocket_port="${websocket_port:-8090}"
scheduler_port="${scheduler_port:-8091}"

echo ""
echo -e "${GREEN}=========================================="
echo "  部署完成！"
echo "==========================================${NC}"
echo ""
echo "服务访问地址："
echo "  前端:        http://服务器IP:${frontend_port}"
echo "  Backend-Web: http://服务器IP:${backend_web_port}"
echo "  WebSocket:   http://服务器IP:${websocket_port}"
echo "  Scheduler:   http://服务器IP:${scheduler_port}"
echo ""
echo "常用命令："
echo "  查看日志: $DC_CMD logs -f"
echo "  停止服务: $DC_CMD down"
echo "  重启服务: $DC_CMD restart"
echo "  更新版本: bash update.sh"
echo ""
