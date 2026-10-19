<?php
/**
 * 目标链接配置 API
 *
 * GET  /api/target.php          -> 返回当前目标链接 { "url": "https://..." }
 * POST /api/target.php          -> 更新目标链接 { "url": "https://...", "password": "xxx" }
 *
 * 存储文件：../data/target.json
 */

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

$dataFile = __DIR__ . '/../data/target.json';
$adminUser = 'admin';   // 管理账号
$adminPass = '223366';  // 管理密码

// 确保 data 目录存在
if (!is_dir(dirname($dataFile))) {
    mkdir(dirname($dataFile), 0755, true);
}

// 默认目标链接
$defaultTarget = 'https://xianyu.jinan.me/Xian_goods/App.php?ClickID=455&te=62';

// 读取当前配置
function readConfig($file, $default) {
    if (!file_exists($file)) {
        return ['url' => $default, 'updated_at' => date('Y-m-d H:i:s')];
    }
    $content = file_get_contents($file);
    $data = json_decode($content, true);
    if (!$data || empty($data['url'])) {
        return ['url' => $default, 'updated_at' => date('Y-m-d H:i:s')];
    }
    return $data;
}

// 写入配置
function writeConfig($file, $url) {
    $data = [
        'url' => $url,
        'updated_at' => date('Y-m-d H:i:s')
    ];
    file_put_contents($file, json_encode($data, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT));
    return $data;
}

// GET：返回当前目标链接
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $config = readConfig($dataFile, $defaultTarget);
    echo json_encode([
        'success' => true,
        'url' => $config['url'],
        'updated_at' => $config['updated_at']
    ]);
    exit;
}

// POST：更新目标链接
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $input = json_decode(file_get_contents('php://input'), true);

    if (!$input || empty($input['url'])) {
        echo json_encode(['success' => false, 'message' => '参数 url 不能为空']);
        http_response_code(400);
        exit;
    }

    // 账号 + 密码校验
    if (empty($input['username']) || empty($input['password'])
        || $input['username'] !== $adminUser || $input['password'] !== $adminPass) {
        echo json_encode(['success' => false, 'message' => '账号或密码错误']);
        http_response_code(403);
        exit;
    }

    $url = trim($input['url']);

    // 校验 URL 格式
    if (!filter_var($url, FILTER_VALIDATE_URL)) {
        echo json_encode(['success' => false, 'message' => 'URL 格式不正确']);
        http_response_code(400);
        exit;
    }

    $config = writeConfig($dataFile, $url);
    echo json_encode([
        'success' => true,
        'message' => '更新成功',
        'url' => $config['url'],
        'updated_at' => $config['updated_at']
    ]);
    exit;
}

echo json_encode(['success' => false, 'message' => '不支持的请求方法']);
http_response_code(405);
