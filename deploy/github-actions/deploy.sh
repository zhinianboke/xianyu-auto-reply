#!/usr/bin/env bash
set -Eeuo pipefail

read -r -a command_parts <<< "${SSH_ORIGINAL_COMMAND:-}"
if [[
  "${#command_parts[@]}" -ne 3 ||
  "${command_parts[0]}" != "deploy" ||
  ! "${command_parts[1]}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ||
  ! "${command_parts[2]}" =~ ^[A-Za-z0-9_-]+$
]]; then
  echo "拒绝未授权的部署命令" >&2
  exit 64
fi

image_tag="${command_parts[1]}"
github_actor="${command_parts[2]}"
ghcr_token="$(cat)"
if [[ -z "${ghcr_token}" ]]; then
  echo "缺少 GHCR 临时令牌" >&2
  exit 65
fi

deploy_dir="/home/ma/xianyu-deploy-v0.2.6"
compose_files=(
  -f docker-compose.deploy.yml
  -f docker-compose.github.yml
)

exec 9>"${deploy_dir}/.github-actions-deploy.lock"
if ! flock -n 9; then
  echo "已有闲鱼服务部署正在执行" >&2
  exit 75
fi

cd "${deploy_dir}"
mkdir -p backups
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="backups/xianyu-before-${image_tag}-${timestamp}.sql.gz"
docker exec xianyu-mysql sh -lc \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' |
  gzip -9 > "${backup_path}"
chmod 600 "${backup_path}"

printf '%s' "${ghcr_token}" |
  docker login ghcr.io -u "${github_actor}" --password-stdin >/dev/null
trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT

if grep -q '^CUSTOM_IMAGE_TAG=' .env; then
  sed -i "s/^CUSTOM_IMAGE_TAG=.*/CUSTOM_IMAGE_TAG=${image_tag}/" .env
else
  printf '\nCUSTOM_IMAGE_TAG=%s\n' "${image_tag}" >> .env
fi

docker compose \
  -p xianyu-auto-reply \
  "${compose_files[@]}" \
  pull backend-web websocket scheduler frontend
docker compose \
  -p xianyu-auto-reply \
  "${compose_files[@]}" \
  up -d --no-deps --force-recreate \
  backend-web websocket scheduler frontend

for container_name in \
  xianyu-backend-web \
  xianyu-websocket \
  xianyu-scheduler \
  xianyu-frontend
do
  health=""
  for _ in $(seq 1 90); do
    health="$(
      docker inspect "${container_name}" \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}'
    )"
    [[ "${health}" == "healthy" ]] && break
    sleep 2
  done
  if [[ "${health}" != "healthy" ]]; then
    echo "${container_name} 未在规定时间内恢复健康" >&2
    exit 1
  fi
done

curl -fsS http://127.0.0.1:8089/health >/dev/null
curl -fsS https://xianyu.xyyamsz.cn/health >/dev/null
echo "闲鱼服务 ${image_tag} 部署成功，备份：${backup_path}"
