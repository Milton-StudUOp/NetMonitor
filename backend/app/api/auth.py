import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.platform import AuditLog, AuthSession, PasswordResetToken, UserAccount
from app.services.account_email import AccountEmailError, build_account_email, send_account_email
from app.services.auth_service import ROLES, create_session, hash_password, token_digest, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class Credentials(BaseModel): username: str = Field(min_length=1, max_length=128); password: str = Field(min_length=1, max_length=256)
class BootstrapInput(Credentials): display_name: str = Field(min_length=1, max_length=128); email: str = Field(min_length=3,max_length=320); bootstrap_token: str = Field(min_length=1); password: str = Field(min_length=9,max_length=256)
class UserInput(BaseModel): username: str = Field(min_length=1,max_length=128); email: str = Field(min_length=3,max_length=320); display_name: str = Field(min_length=1, max_length=128); role: str
class UserUpdate(BaseModel): display_name: str | None = Field(default=None,min_length=1,max_length=128); email: str | None = Field(default=None,min_length=3,max_length=320); role: str | None = None; enabled: bool | None = None; password: str | None = Field(default=None,min_length=9,max_length=256)
class ChangePasswordInput(BaseModel): current_password: str = Field(min_length=1,max_length=256); new_password: str = Field(min_length=9,max_length=256)
class ForgotPasswordInput(BaseModel): email: str = Field(min_length=3,max_length=320)
class ResetPasswordInput(BaseModel): token: str = Field(min_length=6,max_length=6,pattern=r"^[A-Z0-9]{6}$"); new_password: str = Field(min_length=9,max_length=256)

READABLE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RESET_ATTEMPT_WINDOW_SECONDS = 600
RESET_ATTEMPT_LIMIT = 10
_reset_attempts: dict[str, list[float]] = {}

def readable_code(length: int) -> str:
    return "".join(secrets.choice(READABLE_CODE_ALPHABET) for _ in range(length))

def enforce_reset_attempt_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if len(_reset_attempts) > 1000:
        for key, values in list(_reset_attempts.items()):
            if not values or now - values[-1] >= RESET_ATTEMPT_WINDOW_SECONDS:
                _reset_attempts.pop(key, None)
    attempts = [value for value in _reset_attempts.get(client, []) if now - value < RESET_ATTEMPT_WINDOW_SECONDS]
    if len(attempts) >= RESET_ATTEMPT_LIMIT:
        raise HTTPException(429, "Too many recovery attempts. Try again later.")
    attempts.append(now)
    _reset_attempts[client] = attempts

def normalize_email(value: str) -> str:
    value=value.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"): raise HTTPException(422,"Enter a valid email address")
    return value

def view(user): return {"id":user.id,"username":user.username,"email":user.email,"display_name":user.display_name,"role":user.role,"enabled":user.enabled,"must_change_password":user.must_change_password}

@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap(data: BootstrapInput, request: Request, db: AsyncSession = Depends(get_db)):
    configured = get_settings().BOOTSTRAP_TOKEN
    if not configured or not hmac.compare_digest(configured, data.bootstrap_token): raise HTTPException(403, "Bootstrap is not configured or token is invalid")
    if (await db.execute(select(func.count(UserAccount.id)))).scalar(): raise HTTPException(409, "Bootstrap has already been completed")
    user=UserAccount(username=data.username.strip().lower(),email=normalize_email(data.email),display_name=data.display_name.strip(),password_hash=hash_password(data.password),role="ADMINISTRATOR",enabled=True);db.add(user);await db.flush();db.add(AuditLog(action="AUTH_BOOTSTRAP",entity_type="USER",entity_id=str(user.id),summary=f"Initial administrator created: {user.username}"));token,_=await create_session(db,user);return {"token":token,"user":view(user)}

@router.post("/login")
async def login(data: Credentials, request: Request, db: AsyncSession = Depends(get_db)):
    user=(await db.execute(select(UserAccount).where(UserAccount.username==data.username.strip().lower()))).scalar_one_or_none()
    if not user or not user.enabled or not verify_password(data.password,user.password_hash): db.add(AuditLog(action="AUTH_LOGIN_FAILED",entity_type="USER",entity_id=None,summary=f"Failed login for username: {data.username[:64]}"));await db.commit();raise HTTPException(401,"Invalid credentials")
    user.last_login_at=datetime.now(timezone.utc);token,session=await create_session(db,user);db.add(AuditLog(action="AUTH_LOGIN",entity_type="USER",entity_id=str(user.id),summary=f"User logged in: {user.username}"));return {"token":token,"expires_at":session.expires_at,"user":view(user)}

@router.get("/me")
async def me(request:Request): return view(request.state.user)

@router.post("/logout",status_code=204)
async def logout(request:Request):
    request.state.logout_requested = True
    db: AsyncSession = request.state.auth_db
    db.add(AuditLog(action="AUTH_LOGOUT",entity_type="USER",entity_id=str(request.state.user.id),summary=f"User logged out: {request.state.user.username}"))

@router.post("/change-password",status_code=204)
async def change_password(data:ChangePasswordInput,request:Request):
    db: AsyncSession = request.state.auth_db
    user: UserAccount = request.state.user
    if not verify_password(data.current_password,user.password_hash): raise HTTPException(400,"Current password is incorrect")
    if hmac.compare_digest(data.current_password,data.new_password): raise HTTPException(400,"New password must be different")
    user.password_hash=hash_password(data.new_password);user.must_change_password=False
    await db.execute(delete(AuthSession).where(AuthSession.user_id==user.id,AuthSession.id!=request.state.auth_session.id))
    db.add(AuditLog(action="PASSWORD_CHANGE",entity_type="USER",entity_id=str(user.id),summary=f"Password changed by user: {user.username}"))

@router.post("/forgot-password",status_code=202)
async def forgot_password(data:ForgotPasswordInput,db:AsyncSession=Depends(get_db)):
    user=(await db.execute(select(UserAccount).where(UserAccount.email==normalize_email(data.email),UserAccount.enabled==True))).scalar_one_or_none()
    if user:
        code=readable_code(6);now=datetime.now(timezone.utc);settings=get_settings()
        # expires_at is generated by the application in UTC. Do not use the
        # database-server created_at here because database hosts may run in a
        # different timezone and keep the resend cooldown active for hours.
        cooldown_cutoff = now + timedelta(minutes=max(settings.PASSWORD_RESET_MINUTES - 1, 0))
        recent=(await db.execute(select(PasswordResetToken.id).where(PasswordResetToken.user_id==user.id,PasswordResetToken.purpose=="RECOVERY",PasswordResetToken.expires_at>cooldown_cutoff))).scalar_one_or_none()
        if recent is not None: return {"message":"If an enabled account matches that email, a recovery code has been sent."}
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id==user.id,PasswordResetToken.used_at.is_(None)))
        reset_token = PasswordResetToken(user_id=user.id,token_hash=token_digest(code),purpose="RECOVERY",expires_at=now+timedelta(minutes=settings.PASSWORD_RESET_MINUTES),created_at=now)
        db.add(reset_token)
        await db.flush()
        try:
            await send_account_email(db,user.email,build_account_email("RECOVERY",user.display_name,user.username,code,settings.PASSWORD_RESET_MINUTES))
            db.add(AuditLog(action="PASSWORD_RECOVERY_EMAIL_SENT",entity_type="USER",entity_id=str(user.id),summary="Password recovery email delivered"))
        except AccountEmailError:
            await db.delete(reset_token)
            db.add(AuditLog(action="PASSWORD_RECOVERY_EMAIL_FAILED",entity_type="USER",entity_id=str(user.id),summary="Password recovery email delivery failed"))
    return {"message":"If an enabled account matches that email, a recovery code has been sent."}

@router.post("/reset-password",status_code=204)
async def reset_password(data:ResetPasswordInput,request:Request,db:AsyncSession=Depends(get_db)):
    enforce_reset_attempt_limit(request)
    now=datetime.now(timezone.utc);item=(await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash==token_digest(data.token),PasswordResetToken.used_at.is_(None),PasswordResetToken.expires_at>now))).scalar_one_or_none()
    if not item: raise HTTPException(400,"Recovery code is invalid or expired")
    user=await db.get(UserAccount,item.user_id)
    if not user or not user.enabled: raise HTTPException(400,"Recovery code is invalid or expired")
    user.password_hash=hash_password(data.new_password);user.must_change_password=False;item.used_at=now
    if request.client:
        _reset_attempts.pop(request.client.host, None)
    await db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
    db.add(AuditLog(action="PASSWORD_RECOVERY",entity_type="USER",entity_id=str(user.id),summary=f"Password recovered for user: {user.username}"))

@router.get("/users")
async def users(
    request: Request,
    q: str | None = Query(default=None, max_length=320),
    role: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if request.state.user.role!="ADMINISTRATOR":raise HTTPException(403,"Administrator permission required")
    search = (q or "").strip().lower()
    selected_role = (role or "").strip().upper()
    if selected_role and selected_role not in ROLES: raise HTTPException(422,"Invalid role")
    if not search and not selected_role: return []
    query = select(UserAccount)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            func.lower(UserAccount.username).like(pattern),
            func.lower(UserAccount.email).like(pattern),
            func.lower(UserAccount.display_name).like(pattern),
        ))
    if selected_role:
        query = query.where(UserAccount.role == selected_role)
    result = await db.execute(query.order_by(UserAccount.username).limit(limit))
    return [view(item) for item in result.scalars().all()]

@router.post("/users",status_code=201)
async def create_user(data:UserInput,request:Request,db:AsyncSession=Depends(get_db)):
    if request.state.user.role!="ADMINISTRATOR":raise HTTPException(403,"Administrator permission required")
    role=data.role.upper()
    if role not in ROLES:raise HTTPException(422,"Invalid role")
    username=data.username.strip().lower()
    if (await db.execute(select(UserAccount.id).where(UserAccount.username==username))).scalar_one_or_none() is not None:
        raise HTTPException(409,"Username already exists")
    email=normalize_email(data.email)
    if (await db.execute(select(UserAccount.id).where(UserAccount.email==email))).scalar_one_or_none() is not None: raise HTTPException(409,"Email address already exists")
    temporary_password=readable_code(10)
    user=UserAccount(username=username,email=email,display_name=data.display_name.strip(),password_hash=hash_password(temporary_password),role=role,enabled=True,must_change_password=True);db.add(user);await db.flush()
    try: await send_account_email(db,email,build_account_email("INVITE",user.display_name,user.username,temporary_password))
    except AccountEmailError as error: raise HTTPException(503,str(error)) from error
    db.add(AuditLog(action="USER_CREATE",entity_type="USER",entity_id=str(user.id),summary=f"User invited by {request.state.user.username}: {user.username} ({role})"));return view(user)

@router.put("/users/{user_id}")
async def update_user(user_id:int,data:UserUpdate,request:Request,db:AsyncSession=Depends(get_db)):
    if request.state.user.role!="ADMINISTRATOR":raise HTTPException(403,"Administrator permission required")
    user=await db.get(UserAccount,user_id)
    if not user:raise HTTPException(404,"User not found")
    values=data.model_dump(exclude_unset=True)
    if values.get("email"):
        values["email"]=normalize_email(values["email"])
        duplicate=(await db.execute(select(UserAccount.id).where(UserAccount.email==values["email"],UserAccount.id!=user.id))).scalar_one_or_none()
        if duplicate is not None: raise HTTPException(409,"Email address already exists")
    if values.get("role"):
        values["role"]=values["role"].upper()
        if values["role"] not in ROLES:raise HTTPException(422,"Invalid role")
    if user.id==request.state.user.id and (values.get("enabled") is False or values.get("role") not in {None,"ADMINISTRATOR"}):raise HTTPException(400,"The active administrator cannot disable or demote their own account")
    password=values.pop("password",None)
    for key,value in values.items():setattr(user,key,value.strip() if isinstance(value,str) else value)
    if password:user.password_hash=hash_password(password)
    db.add(AuditLog(action="USER_UPDATE",entity_type="USER",entity_id=str(user.id),summary=f"User updated by {request.state.user.username}: {user.username}"));return view(user)
