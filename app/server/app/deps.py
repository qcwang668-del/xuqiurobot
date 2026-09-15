from fastapi import Depends, Header, HTTPException

from . import db, security


def current_user(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    uid = security.parse_token(authorization[7:], db.get_config("auth_secret"))
    if uid is None:
        raise HTTPException(status_code=401, detail="登录已过期")
    user = db.query_one("SELECT id,username,name,role FROM users WHERE id=?", (uid,))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_roles(*roles):
    def checker(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="无权限执行该操作")
        return user
    return checker
