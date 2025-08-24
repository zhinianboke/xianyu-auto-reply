#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专门用于调试闲鱼接口响应数据的脚本
"""

import asyncio
import aiohttp
import json
import urllib.parse
import time
import hashlib

def trans_cookies(cookies_str: str) -> dict:
    """将cookies字符串转换为字典"""
    if not cookies_str:
        return {}
        
    cookies = {}
    for cookie in cookies_str.split("; "):
        if "=" in cookie:
            key, value = cookie.split("=", 1)
            cookies[key] = value
    return cookies

def generate_sign(t: str, token: str, data: str) -> str:
    """生成签名"""
    app_key = "34839810"
    msg = f"{token}&{t}&{app_key}&{data}"
    
    # 使用MD5生成签名
    md5_hash = hashlib.md5()
    md5_hash.update(msg.encode('utf-8'))
    return md5_hash.hexdigest()

async def debug_xianyu_response():
    """调试闲鱼接口响应"""
    
    print("🔍 调试闲鱼智能分类推荐接口响应数据")
    print("=" * 60)
    
    # 测试数据
    test_data = {
        "title": "iPhone 15 Pro Max",
        "description": "全新未拆封的iPhone 15 Pro Max，256GB存储，深空黑色，支持5G网络，A17 Pro芯片，钛金属边框",
        "lockCpv": False,
        "multiSKU": False,
        "publishScene": "mainPublish",
        "scene": "newPublishChoice",
        "uniqueCode": str(int(time.time() * 1000))
    }
    
    # 固定Cookie字符串
    cookie_str = "cna=2x0VIEthuBgCAQFBy07P5aax; t=92064eac9aab68795e909c84b6666cd4; tracknick=xy771982658888; _hvn_lgc_=77; isg=BFNThiggP-HZDPMg_KngAC0L4td9COfK5wirBAVwrnKphHEmjdtsHpLXuvrqJD_C; cookie2=1d8f3898faa1abb58159790a3802e3a3; _samesite_flag_=true; sdkSilent=1756085421522; _tb_token_=83b7e178e4b5; xlly_s=1; sgcookie=E100JrXTnL7eFQiRIJStkPX%2FZJxZtFmn8IWMEQUTVeR%2BK4TC8vd3U6WNxRg36qan9rnlIl8HcDt7nJmiIbwnTBUSFSAvafcrZKU56HA20aPhfD%2FloEoiEGK%2Bis3ViFXhA5Q6; csg=d2659320; unb=2219383264998; havana_lgc2_77=eyJoaWQiOjIyMTkzODMyNjQ5OTgsInNnIjoiZjM3ZDNjZTQ0ZDBhYzliOTc3NDAyNTEzMGI3ODk1YTgiLCJzaXRlIjo3NywidG9rZW4iOiIxVEFJZlFvS0wzZklKeVlUdnM5OVdndyJ9; havana_lgc_exp=1758591062196; mtop_partitioned_detect=1; _m_h5_tk=c98d7a32c14f4fe072ffe828166b6ac5_1756031965221; _m_h5_tk_enc=9d42daa408b78fd39accfaca44e9af57; tfstk=gtMKHWAOvFY3MQ_Fv4AGqE02dL-i9CmE-2ofEz4hNV3tcm73Nv2ny_3n44VW8JD-W0ov48c3-gIEBqBlKeREVTeuFEYDnKmFY8yWoNOZ5f7UDu4WEWZQ1JrkZBbhWKmEYGsdPnc6ngdA9fqQP4NQ1NZ05ksQA4_1CPrzVwZ5dhn_7PZQA8N55GZ8c_1IP8ttfPr7Fkg7Ohn_7uw7PbKwyPsQrThpifd-AtCNeTHTvWURKyBRb3qQ9riQWETSBZPLlDaOeEXzitU87xTM6cuxO2qZyKLThjuteSwJpZrK1me_--OA6Jni8xeIHeB3jRzUGbN9ApiTpyF-e5sVsJhS8YFE9g-qfJgZgrPB_FrtKxV8u5Q6RcmTRSh--FW7-jnsWSDGSt2jgVH8G-sruxDYiD_0kufBXhCPaWZN0TfpDrV1i2rToHpRa_PwblUDXhCPaWZaXrxpJ_5z_h5.."
    
    # 构建请求URL和参数
    base_url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.kgraph.property.recommend/2.0/"
    timestamp = str(int(time.time() * 1000))
    
    # 从Cookie中提取token
    token = ""
    try:
        cookies_dict = trans_cookies(cookie_str)
        m_h5_tk = cookies_dict.get('_m_h5_tk', '')
        if m_h5_tk and '_' in m_h5_tk:
            token = m_h5_tk.split('_')[0]
            print(f"📋 从Cookie中提取到token: {token}")
        else:
            print("❌ Cookie中未找到有效的_m_h5_tk token")
    except Exception as e:
        print(f"❌ 解析Cookie失败: {str(e)}")
    
    # 生成签名
    data_json = json.dumps(test_data, ensure_ascii=False, separators=(',', ':'))
    sign = generate_sign(timestamp, token, data_json)
    
    # URL参数
    url_params = {
        "jsv": "2.7.2",
        "appKey": "34839810",
        "t": timestamp,
        "sign": sign,
        "v": "2.0",
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": "mtop.taobao.idle.kgraph.property.recommend",
        "sessionOption": "AutoLoginOnly"
    }
    
    url_with_params = base_url + "?" + urllib.parse.urlencode(url_params)
    encoded_data = urllib.parse.urlencode({"data": data_json})
    
    # 请求头
    headers = {
        "accept": "application/json",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "Referer": "https://www.goofish.com/",
        "cookie": cookie_str
    }
    
    print(f"🌐 请求URL: {url_with_params}")
    print(f"🔐 生成的签名: {sign}")
    print(f"⏰ 时间戳: {timestamp}")
    print(f"📦 请求数据: {data_json}")
    print("-" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url_with_params,
                headers=headers,
                data=encoded_data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                print(f"📊 HTTP状态码: {response.status}")
                print(f"📋 响应头: {dict(response.headers)}")
                print("-" * 60)
                
                if response.status == 200:
                    try:
                        response_data = await response.json()
                        print("✅ 成功获取JSON响应数据:")
                        print("🔍 完整响应数据结构:")
                        print("=" * 60)
                        print(json.dumps(response_data, indent=2, ensure_ascii=False))
                        print("=" * 60)
                        
                        # 分析响应数据结构
                        print("\n📊 响应数据分析:")
                        print(f"- ret字段: {response_data.get('ret', 'N/A')}")
                        print(f"- data字段存在: {'是' if 'data' in response_data else '否'}")
                        
                        if 'data' in response_data:
                            data = response_data['data']
                            print(f"- data类型: {type(data)}")
                            if isinstance(data, dict):
                                print(f"- data字段数量: {len(data)}")
                                print(f"- data主要字段: {list(data.keys())}")
                                
                                if 'cpvList' in data:
                                    cpv_list = data['cpvList']
                                    print(f"- cpvList类型: {type(cpv_list)}")
                                    if isinstance(cpv_list, str):
                                        try:
                                            cpv_parsed = json.loads(cpv_list)
                                            print(f"- cpvList解析后类型: {type(cpv_parsed)}")
                                            print(f"- cpvList项目数量: {len(cpv_parsed) if isinstance(cpv_parsed, list) else 'N/A'}")
                                        except:
                                            print("- cpvList解析失败")
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {e}")
                        response_text = await response.text()
                        print(f"原始响应内容: {response_text}")
                        
                else:
                    print(f"❌ HTTP请求失败，状态码: {response.status}")
                    response_text = await response.text()
                    print(f"错误响应内容: {response_text}")
                    
    except Exception as e:
        print(f"💥 请求异常: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_xianyu_response())
