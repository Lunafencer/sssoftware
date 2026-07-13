/**
 * 角色枚举单一来源（FIX5 第 17 项）
 * - 前端角色：frontline | auditor | admin | guest
 * - 后端角色：worker | leader | auditor | admin
 * 所有角色相关的映射、标签、菜单权限都从这里派生，避免散落硬编码。
 */

export type FrontendRole = 'frontline' | 'auditor' | 'admin' | 'guest'
export type BackendRole = 'worker' | 'leader' | 'auditor' | 'admin'

/** 兼容旧引用：Role 即前端角色 */
export type Role = FrontendRole

export const FRONTEND_ROLES: FrontendRole[] = ['frontline', 'auditor', 'admin', 'guest']

export const ROLE_LABEL: Record<FrontendRole, string> = {
  frontline: '一线检修员',
  auditor:   '知识审核员',
  admin:     '系统管理员',
  guest:     '访客'
}

/** 后端 role 字段 → 前端权限角色 */
export function mapBackendRole(r: string | undefined): FrontendRole {
  switch ((r || '').toLowerCase()) {
    case 'admin':    return 'admin'
    case 'leader':   return 'auditor'
    case 'auditor':  return 'auditor'
    case 'guest':    return 'guest'
    case 'worker':
    case 'frontline':
    default:         return 'frontline'
  }
}

/** 前端角色 → 后端角色（管理员创建/修改账户时使用） */
export function mapFrontendRole(r: FrontendRole): BackendRole {
  switch (r) {
    case 'admin':     return 'admin'
    case 'auditor':   return 'auditor'
    case 'frontline':
    case 'guest':
    default:          return 'worker'
  }
}

/** 管理员可分配的角色（不含 guest） */
export const ASSIGNABLE_ROLES: FrontendRole[] = ['frontline', 'auditor', 'admin']

export function isAuditorRole(r: FrontendRole | undefined): boolean {
  return r === 'auditor' || r === 'admin'
}
