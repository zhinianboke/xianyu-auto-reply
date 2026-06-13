"""
支付相关 API 路由

功能：
1. 创建充值订单（当面付二维码）
2. 支付宝异步通知回调（无需认证）
3. 查询充值订单状态
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.recharge_service import RechargeService
from app.services.settlement_service import SettlementService
from common.models.user import User
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/payment", tags=["支付管理"])


class RechargeRequest(BaseModel):
    """充值请求"""
    amount: str = Field(..., description="充值金额，例如：10.00")


class WithdrawRequest(BaseModel):
    """提现请求"""
    amount: str = Field(..., description="提现金额，例如：10.00")


@router.post("/recharge")
async def create_recharge(
    payload: RechargeRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """创建充值订单，返回支付宝当面付二维码"""
    service = RechargeService(session)
    result = await service.create_recharge_order(current_user.id, payload.amount)
    return result


@router.post("/alipay/notify")
async def alipay_notify(
    request: Request,
) -> PlainTextResponse:
    """支付宝异步通知回调（无需登录认证）

    支付宝通知需要返回纯文本 "success" 或 "failure"
    """
    from common.db.session import async_session_maker

    # 获取表单数据
    form_data = await request.form()
    notify_data = {k: v for k, v in form_data.items()}

    # 使用独立会话处理回调（回调无用户上下文）
    async with async_session_maker() as session:
        service = RechargeService(session)
        ok = await service.handle_alipay_notify(notify_data)

    if ok:
        return PlainTextResponse("success")
    return PlainTextResponse("failure")


@router.get("/recharge/{order_no}")
async def get_recharge_status(
    order_no: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """查询充值订单状态"""
    service = RechargeService(session)
    result = await service.get_order_status(order_no, current_user.id)
    if not result:
        return {"success": False, "code": 0, "message": "订单不存在", "data": None}
    return {"success": True, "code": 0, "message": None, "data": result}


@router.post("/withdraw", response_model=ApiResponse)
async def create_withdraw(
    payload: WithdrawRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """创建提现申请记录，状态为待审核"""
    service = SettlementService(session)
    return await service.create_withdraw_record(current_user.id, payload.amount)


@router.get("/settlement-records")
async def get_settlement_records(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
) -> Dict[str, Any]:
    """分页查询当前用户结算记录，按创建时间倒序返回"""
    service = SettlementService(session)
    return await service.get_settlement_records(current_user.id, page, page_size)


@router.get("/withdraw/review")
async def review_withdraw(
    id: int = Query(..., description="结算记录ID"),
    action: str = Query(..., description="审核动作：approve-通过，reject-拒绝"),
    token: str = Query(..., description="审核令牌"),
):
    """审核提现申请（无需登录，通过令牌验证）
    
    approve：直接通过审核，返回 JSON。
    reject：显示填写拒绝原因的 HTML 表单页面。
    """
    from fastapi.responses import HTMLResponse
    from app.services.settlement_service import verify_review_token

    if action == 'approve':
        # 安全：GET 请求不直接变更审核状态，避免邮件预取/链接扫描器误触发通过审批。
        # 先校验令牌，再展示二次确认页面，由管理员点击按钮以 POST 方式真正执行通过。
        if not verify_review_token(id, 'approve', token):
            html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>错误</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px;color:#ef4444">
<h2>无效的审核令牌</h2></body></html>"""
            return HTMLResponse(content=html, status_code=400)

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>通过提现申请</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f4f7fa;">
<div style="background:#fff;border-radius:16px;padding:40px;box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:440px;width:90%">
  <div style="width:64px;height:64px;border-radius:50%;background:#10b981;margin:0 auto 20px;display:flex;align-items:center;justify-content:center">
    <span style="color:#fff;font-size:28px">✓</span>
  </div>
  <h2 style="text-align:center;margin:0 0 24px;color:#1a1a2e">通过提现申请 #{id}</h2>
  <div id="form-area">
    <p style="color:#374151;font-size:14px;text-align:center;margin-bottom:20px">请确认通过该提现申请，确认后将进入打款流程。</p>
    <div id="err-msg" style="display:none;color:#ef4444;font-size:13px;margin-bottom:12px;text-align:center"></div>
    <div style="display:flex;gap:12px">
      <button id="cancelBtn" type="button" onclick="history.back()"
        style="flex:1;padding:12px;background:#f3f4f6;border:none;border-radius:8px;font-size:15px;cursor:pointer;color:#374151">取消</button>
      <button id="submitBtn" type="button" onclick="doApprove()"
        style="flex:1;padding:12px;background:#10b981;border:none;border-radius:8px;font-size:15px;cursor:pointer;color:#fff;font-weight:600">确认通过</button>
    </div>
  </div>
  <div id="result-area" style="display:none;text-align:center">
    <div id="result-icon" style="font-size:48px;margin-bottom:16px"></div>
    <h3 id="result-msg" style="margin:0 0 8px;color:#1a1a2e"></h3>
    <p style="color:#6b7280;font-size:14px">可关闭此页面</p>
  </div>
</div>
<script>
function doApprove() {{
  var btn = document.getElementById('submitBtn');
  var cancelBtn = document.getElementById('cancelBtn');
  var errEl = document.getElementById('err-msg');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = '处理中...';
  btn.style.opacity = '0.6';
  btn.style.cursor = 'not-allowed';
  cancelBtn.disabled = true;
  cancelBtn.style.opacity = '0.4';
  cancelBtn.style.cursor = 'not-allowed';
  var body = new URLSearchParams();
  body.append('id', '{id}');
  body.append('token', '{token}');
  fetch('/api/v1/payment/withdraw/approve', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: body.toString()
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    document.getElementById('form-area').style.display = 'none';
    var ra = document.getElementById('result-area');
    ra.style.display = 'block';
    var icon = document.getElementById('result-icon');
    var msg = document.getElementById('result-msg');
    if (data.success) {{
      icon.textContent = '✅';
      msg.textContent = data.message || '操作成功';
      msg.style.color = '#10b981';
    }} else {{
      icon.textContent = '❌';
      msg.textContent = data.message || '操作失败';
      msg.style.color = '#ef4444';
    }}
  }})
  .catch(function(e) {{
    btn.disabled = false;
    btn.textContent = '确认通过';
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
    cancelBtn.disabled = false;
    cancelBtn.style.opacity = '1';
    cancelBtn.style.cursor = 'pointer';
    errEl.textContent = '网络错误，请重试';
    errEl.style.display = 'block';
  }});
}}
</script>
</body></html>"""
        return HTMLResponse(content=html)

    # reject：先验证 token，再展示填写原因的表单
    if not verify_review_token(id, 'reject', token):
        html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>错误</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px;color:#ef4444">
<h2>无效的审核令牌</h2></body></html>"""
        return HTMLResponse(content=html, status_code=400)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>拒绝提现申请</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f4f7fa;">
<div id="card" style="background:#fff;border-radius:16px;padding:40px;box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:440px;width:90%">
  <div style="width:64px;height:64px;border-radius:50%;background:#ef4444;margin:0 auto 20px;display:flex;align-items:center;justify-content:center">
    <span style="color:#fff;font-size:28px">✗</span>
  </div>
  <h2 style="text-align:center;margin:0 0 24px;color:#1a1a2e">拒绝提现申请 #{id}</h2>
  <div id="form-area">
    <div style="margin-bottom:16px">
      <label style="display:block;font-size:14px;color:#374151;margin-bottom:6px">拒绝原因（可选）</label>
      <textarea id="reject_reason" rows="4" placeholder="请输入拒绝原因，将通知用户..."
        style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;resize:vertical;outline:none"></textarea>
    </div>
    <div id="err-msg" style="display:none;color:#ef4444;font-size:13px;margin-bottom:12px;text-align:center"></div>
    <div style="display:flex;gap:12px">
      <button id="cancelBtn" type="button" onclick="history.back()"
        style="flex:1;padding:12px;background:#f3f4f6;border:none;border-radius:8px;font-size:15px;cursor:pointer;color:#374151">取消</button>
      <button id="submitBtn" type="button" onclick="doReject()"
        style="flex:1;padding:12px;background:#ef4444;border:none;border-radius:8px;font-size:15px;cursor:pointer;color:#fff;font-weight:600">确认拒绝</button>
    </div>
  </div>
  <div id="result-area" style="display:none;text-align:center">
    <div id="result-icon" style="font-size:48px;margin-bottom:16px"></div>
    <h3 id="result-msg" style="margin:0 0 8px;color:#1a1a2e"></h3>
    <p style="color:#6b7280;font-size:14px">可关闭此页面</p>
  </div>
</div>
<script>
function doReject() {{
  var btn = document.getElementById('submitBtn');
  var cancelBtn = document.getElementById('cancelBtn');
  var reason = document.getElementById('reject_reason').value;
  var errEl = document.getElementById('err-msg');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = '处理中...';
  btn.style.opacity = '0.6';
  btn.style.cursor = 'not-allowed';
  cancelBtn.disabled = true;
  cancelBtn.style.opacity = '0.4';
  cancelBtn.style.cursor = 'not-allowed';
  var body = new URLSearchParams();
  body.append('id', '{id}');
  body.append('token', '{token}');
  body.append('reject_reason', reason);
  fetch('/api/v1/payment/withdraw/reject', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: body.toString()
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    document.getElementById('form-area').style.display = 'none';
    var ra = document.getElementById('result-area');
    ra.style.display = 'block';
    var icon = document.getElementById('result-icon');
    var msg = document.getElementById('result-msg');
    if (data.success) {{
      icon.textContent = '✅';
      msg.textContent = data.message || '操作成功';
      msg.style.color = '#10b981';
    }} else {{
      icon.textContent = '❌';
      msg.textContent = data.message || '操作失败';
      msg.style.color = '#ef4444';
    }}
  }})
  .catch(function(e) {{
    btn.disabled = false;
    btn.textContent = '确认拒绝';
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
    cancelBtn.disabled = false;
    cancelBtn.style.opacity = '1';
    cancelBtn.style.cursor = 'pointer';
    errEl.textContent = '网络错误，请重试';
    errEl.style.display = 'block';
  }});
}}
</script>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/withdraw/approve")
async def do_approve_withdraw(request: Request):
    """处理通过提现的二次确认提交（POST），返回 JSON 供前端 fetch 使用

    安全：通过审批必须经由 POST 执行，配合令牌校验，避免 GET 链接被预取/扫描误触发。
    """
    from app.services.settlement_service import review_withdraw_record
    from fastapi.responses import JSONResponse

    form = await request.form()
    record_id = int(form.get('id', 0))
    token = str(form.get('token', ''))

    result = await review_withdraw_record(record_id, 'approve', token)
    return JSONResponse(content=result)


@router.post("/withdraw/reject")
async def do_reject_withdraw(request: Request):
    """处理拒绝提现的表单提交（带拒绝原因），返回 JSON 供前端 fetch 使用"""
    from app.services.settlement_service import review_withdraw_record
    from fastapi.responses import JSONResponse

    form = await request.form()
    record_id = int(form.get('id', 0))
    token = str(form.get('token', ''))
    reject_reason = str(form.get('reject_reason', ''))

    result = await review_withdraw_record(record_id, 'reject', token, reject_reason)
    return JSONResponse(content=result)
