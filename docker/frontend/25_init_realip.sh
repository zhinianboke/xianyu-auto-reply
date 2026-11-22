#!/bin/sh
# 闲鱼前端入口初始化：从实际默认路由识别宿主机网关，仅信任 loopback 与网关单地址。
set -eu

route_file=/proc/net/route
realip_file=/etc/nginx/trusted_proxy_realip.conf
if [ ! -r "$route_file" ]; then
    echo '[错误] 无法读取 Docker 默认路由，拒绝启动未配置可信代理的 Nginx' >&2
    exit 1
fi

# 默认路由使用小端十六进制 IPv4；多条路由时选择 metric 最小的一条。
gateway_hex=$(awk '
    $2 == "00000000" && $3 != "00000000" {
        if (!found || $7 + 0 < metric) {
            gateway = $3; metric = $7 + 0; found = 1
        }
    }
    END { if (found) print gateway }
' "$route_file")
case "$gateway_hex" in
    ????????) ;;
    *) echo '[错误] Docker 默认网关缺失或格式错误' >&2; exit 1 ;;
esac
case "$gateway_hex" in
    *[!0-9a-fA-F]*) echo '[错误] Docker 默认网关不是合法十六进制 IPv4' >&2; exit 1 ;;
esac

gateway_ip=$(awk -v raw="$gateway_hex" 'BEGIN {
    raw = toupper(raw)
    for (i = 1; i <= 4; i++) {
        offset = 9 - i * 2
        octet[i] = (index("0123456789ABCDEF", substr(raw, offset, 1)) - 1) * 16 \
            + index("0123456789ABCDEF", substr(raw, offset + 1, 1)) - 1
    }
    if (octet[1] == 0 || octet[1] == 127 || octet[1] >= 224) exit 1
    printf "%d.%d.%d.%d", octet[1], octet[2], octet[3], octet[4]
}') || { echo '[错误] Docker 默认网关不是合法单播 IPv4' >&2; exit 1; }
case "$gateway_ip" in
    0.*|127.*|255.*|'') echo '[错误] Docker 默认网关地址无效' >&2; exit 1 ;;
esac

printf '%s\n' \
    '# 自动生成：仅信任同机反代的实际连接来源，不信任公网声明。' \
    'real_ip_header X-Forwarded-For;' \
    'real_ip_recursive on;' \
    'set_real_ip_from 127.0.0.1/32;' \
    'set_real_ip_from ::1/128;' \
    "set_real_ip_from $gateway_ip/32;" > "$realip_file"

# 配置错误必须在入口初始化时明确失败，不能继续以错误 IP 启动业务链路。
nginx -t || { echo '[错误] 可信代理 Nginx 配置校验失败' >&2; exit 1; }
echo "[信息] 闲鱼前端可信宿主机网关已配置：$gateway_ip/32"
