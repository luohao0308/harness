# 手动测试指南

**项目**: Agent Harness - Onboarding v1 + AuthN/AuthZ v2 SSO  
**测试日期**: 2026-06-15  
**测试人员**: ___________  
**测试环境**: ___________

---

## 📋 测试前准备

### 1. 环境启动

```bash
# Backend
cd services/api-server
python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/agent-console
npm run dev
```

### 2. 数据库准备

```bash
cd services/api-server
alembic upgrade head
```

### 3. 环境变量检查

确保以下环境变量已配置：
- `DATABASE_URL`
- `SECRET_KEY`
- `SAML_ENTITY_ID`
- `OKTA_METADATA_URL` (可选)
- `AZURE_AD_METADATA_URL` (可选)

---

## 🎯 测试套件 1: Onboarding Wizard (首次运行向导)

### 测试场景 1.1: 完整流程 (Happy Path)

**前置条件**: 数据库为空，首次访问

**测试步骤**:

1. **访问应用**
   - [ ] 打开浏览器访问 `http://localhost:5173`
   - [ ] 应自动跳转到 `/onboarding`
   - [ ] 验证页面标题: "首次运行设置"

2. **Step 1: 欢迎 / Provider选择**
   - [ ] 验证显示 "Step 1 of 4"
   - [ ] 看到3个Provider选项: OpenAI, DeepSeek, Claude
   - [ ] 点击 "DeepSeek" 卡片
   - [ ] 验证卡片边框变为深色 (选中状态)
   - [ ] 点击 "下一步" 按钮
   - [ ] 页面进入Step 2

3. **Step 2: 配置模型连接**
   - [ ] 验证显示 "Step 2 of 4"
   - [ ] 验证标题: "配置模型连接"
   - [ ] 看到两个输入框: Endpoint URL, API Key
   - [ ] 输入 Endpoint: `https://api.deepseek.com`
   - [ ] 输入 API Key: `sk-test-key-12345`
   - [ ] 点击 "保存并继续" 按钮
   - [ ] 验证出现成功提示
   - [ ] 页面进入Step 3

4. **Step 3: 创建第一个智能体**
   - [ ] 验证显示 "Step 3 of 4"
   - [ ] 验证标题: "创建第一个智能体"
   - [ ] 看到3个模板: 研究助手, 代码审查, 数据分析
   - [ ] 点击 "研究助手" 卡片
   - [ ] 验证 Agent ID 输入框预填充: "first-run-agent"
   - [ ] 点击 "从模板创建" 按钮
   - [ ] 验证出现成功提示: "首个智能体已创建"
   - [ ] 页面进入Step 4

5. **Step 4: 运行演示任务**
   - [ ] 验证显示 "Step 4 of 4"
   - [ ] 验证标题: "运行演示任务"
   - [ ] 点击 "触发演示" 按钮
   - [ ] 验证出现成功提示: "演示运行已创建"
   - [ ] 验证显示任务ID: "demo-task-001"
   - [ ] 点击 "完成设置" 按钮
   - [ ] 验证跳转到首页 `/`

6. **验证向导完成**
   - [ ] 刷新页面
   - [ ] 验证不再跳转到 `/onboarding`
   - [ ] 验证首页正常显示

**预期结果**: ✅ 所有步骤顺利完成，向导标记为已完成

---

### 测试场景 1.2: 步骤导航

**测试步骤**:

1. **前进/后退按钮**
   - [ ] 在Step 2点击 "上一步"
   - [ ] 验证返回Step 1
   - [ ] 验证之前选择的Provider仍然被选中
   - [ ] 点击 "下一步" 返回Step 2
   - [ ] 验证之前输入的配置仍然存在

2. **步骤指示器点击**
   - [ ] 点击步骤指示器中的 "Step 3"
   - [ ] 验证跳转到Step 3
   - [ ] 验证状态保持一致

**预期结果**: ✅ 导航流畅，状态持久化正确

---

### 测试场景 1.3: 表单验证

**测试步骤**:

1. **Step 2: 空字段验证**
   - [ ] 进入Step 2
   - [ ] 不填写任何字段，直接点击 "保存并继续"
   - [ ] 验证出现错误提示: "Endpoint URL is required"
   - [ ] 验证出现错误提示: "API Key is required"

2. **Step 2: URL格式验证**
   - [ ] 输入无效URL: "not-a-url"
   - [ ] 点击 "保存并继续"
   - [ ] 验证出现错误提示: "Please enter a valid URL"

3. **Step 3: Agent ID验证**
   - [ ] 进入Step 3
   - [ ] 清空Agent ID输入框
   - [ ] 点击 "从模板创建"
   - [ ] 验证出现错误提示: "Agent ID is required"

**预期结果**: ✅ 所有验证按预期工作

---

## 🎯 测试套件 2: SSO/SAML 登录

### 测试场景 2.1: 单Provider登录

**前置条件**: 数据库中配置了1个Okta SAML Provider

**测试步骤**:

1. **访问登录页**
   - [ ] 访问 `http://localhost:5173/login`
   - [ ] 验证页面标题: "登录"
   - [ ] 看到 "使用Okta登录" 按钮

2. **发起SSO登录**
   - [ ] 点击 "使用Okta登录" 按钮
   - [ ] 验证出现加载状态
   - [ ] 验证浏览器开始重定向到IdP (Okta)

**预期结果**: ✅ SSO流程正确启动

---

### 测试场景 2.2: 多Provider选择

**前置条件**: 数据库中配置了2个SAML Provider (Okta, Azure AD)

**测试步骤**:

1. **访问登录页**
   - [ ] 访问 `http://localhost:5173/login`
   - [ ] 验证看到2个SSO按钮: "使用Okta登录", "使用Azure AD登录"

2. **选择Provider**
   - [ ] 点击 "使用Azure AD登录"
   - [ ] 验证出现加载状态
   - [ ] 验证浏览器重定向到Azure AD

**预期结果**: ✅ 多Provider显示正确，各自独立工作

---

### 测试场景 2.3: SSO错误处理

**测试步骤**:

1. **IdP不可用**
   - [ ] 模拟IdP错误 (通过后端mock或配置错误的URL)
   - [ ] 点击SSO登录按钮
   - [ ] 验证出现错误提示: "IdP is temporarily unavailable"
   - [ ] 验证页面不崩溃，仍可重试

2. **网络错误**
   - [ ] 断开网络连接
   - [ ] 点击SSO登录按钮
   - [ ] 验证出现网络错误提示
   - [ ] 恢复网络
   - [ ] 验证可以重试

**预期结果**: ✅ 错误优雅处理，用户可重试

---

## 🎯 测试套件 3: Admin SAML配置

### 测试场景 3.1: SAML Provider列表

**前置条件**: 管理员身份登录

**测试步骤**:

1. **访问SAML配置页**
   - [ ] 访问 `http://localhost:5173/admin/sso/saml`
   - [ ] 验证页面标题: "SAML Provider管理"
   - [ ] 验证看到Provider列表 (表格形式)

2. **列表显示内容**
   - [ ] 验证每个Provider显示: Name, Entity ID, Status, Actions
   - [ ] 验证Status有颜色标识 (Active=绿色, Inactive=灰色)
   - [ ] 验证Actions有: Edit, Delete, Test Connection

**预期结果**: ✅ 列表正确显示所有Provider

---

### 测试场景 3.2: 创建SAML Provider

**测试步骤**:

1. **打开创建表单**
   - [ ] 点击 "Add New Provider" 按钮
   - [ ] 验证弹出模态对话框
   - [ ] 验证标题: "Create SAML Provider"

2. **填写表单 (Metadata URL方式)**
   - [ ] 输入Name: "OneLogin"
   - [ ] 输入Entity ID: "https://app.example.com/saml/onelogin"
   - [ ] 输入SSO URL: "https://onelogin.example.com/sso"
   - [ ] 选择 "Use Metadata URL"
   - [ ] 输入Metadata URL: "https://onelogin.example.com/metadata.xml"
   - [ ] 点击 "Create" 按钮

3. **验证创建成功**
   - [ ] 验证出现成功提示: "Provider created successfully"
   - [ ] 验证模态对话框关闭
   - [ ] 验证列表中出现新的Provider "OneLogin"

**预期结果**: ✅ Provider创建成功并显示在列表中

---

### 测试场景 3.3: 创建SAML Provider (XML方式)

**测试步骤**:

1. **打开创建表单**
   - [ ] 点击 "Add New Provider" 按钮

2. **填写表单 (Metadata XML方式)**
   - [ ] 输入Name: "Google Workspace"
   - [ ] 输入Entity ID: "https://app.example.com/saml/google"
   - [ ] 输入SSO URL: "https://accounts.google.com/sso"
   - [ ] 选择 "Upload Metadata XML"
   - [ ] 上传XML文件或粘贴XML内容
   - [ ] 点击 "Create" 按钮

3. **验证创建成功**
   - [ ] 验证出现成功提示
   - [ ] 验证列表中出现新Provider

**预期结果**: ✅ XML方式创建成功

---

### 测试场景 3.4: 编辑SAML Provider

**测试步骤**:

1. **打开编辑表单**
   - [ ] 在列表中找到 "Okta" Provider
   - [ ] 点击 "Edit" 按钮
   - [ ] 验证弹出模态对话框
   - [ ] 验证标题: "Edit SAML Provider"
   - [ ] 验证所有字段预填充当前值

2. **修改字段**
   - [ ] 将Name改为: "Okta Production"
   - [ ] 点击 "Save" 按钮

3. **验证更新成功**
   - [ ] 验证出现成功提示: "Provider updated successfully"
   - [ ] 验证列表中Name已更新为 "Okta Production"

**预期结果**: ✅ Provider更新成功

---

### 测试场景 3.5: 删除SAML Provider

**测试步骤**:

1. **触发删除**
   - [ ] 在列表中找到要删除的Provider
   - [ ] 点击 "Delete" 按钮
   - [ ] 验证出现确认对话框: "Are you sure you want to delete this provider?"

2. **确认删除**
   - [ ] 点击 "Confirm" 按钮
   - [ ] 验证出现成功提示: "Provider deleted successfully"
   - [ ] 验证Provider从列表中消失

3. **取消删除**
   - [ ] 对另一个Provider点击 "Delete"
   - [ ] 在确认对话框点击 "Cancel"
   - [ ] 验证对话框关闭
   - [ ] 验证Provider仍在列表中

**预期结果**: ✅ 删除和取消都工作正常

---

### 测试场景 3.6: 测试连接

**测试步骤**:

1. **测试成功场景**
   - [ ] 在列表中找到配置正确的Provider
   - [ ] 点击 "Test Connection" 按钮
   - [ ] 验证出现加载状态
   - [ ] 验证出现成功提示: "Connection test successful"
   - [ ] 验证Status列更新为 "✓ Tested"

2. **测试失败场景**
   - [ ] 编辑Provider，将Metadata URL改为无效URL
   - [ ] 点击 "Test Connection" 按钮
   - [ ] 验证出现错误提示，包含错误详情
   - [ ] 验证Status列显示错误状态

**预期结果**: ✅ 测试连接正常工作，反馈清晰

---

### 测试场景 3.7: 表单验证

**测试步骤**:

1. **必填字段验证**
   - [ ] 点击 "Add New Provider"
   - [ ] 不填写任何字段，直接点击 "Create"
   - [ ] 验证出现错误提示: "Name is required"
   - [ ] 验证出现错误提示: "Entity ID is required"
   - [ ] 验证出现错误提示: "SSO URL is required"

2. **URL格式验证**
   - [ ] 输入Entity ID: "not-a-url"
   - [ ] 点击Create
   - [ ] 验证出现错误: "Please enter a valid URL"

3. **Metadata必选验证**
   - [ ] 填写Name, Entity ID, SSO URL
   - [ ] 不选择Metadata URL也不上传XML
   - [ ] 点击Create
   - [ ] 验证出现错误: "Either Metadata URL or XML is required"

**预期结果**: ✅ 所有验证规则生效

---

## 🎯 测试套件 4: 无障碍 (Accessibility)

### 测试场景 4.1: 键盘导航

**测试步骤**:

1. **Onboarding向导**
   - [ ] 访问 `/onboarding`
   - [ ] 使用Tab键导航
   - [ ] 验证所有可交互元素可获得焦点
   - [ ] 验证焦点顺序符合逻辑 (从上到下，从左到右)
   - [ ] 使用Enter/Space键激活按钮
   - [ ] 验证功能正常工作

2. **SSO登录页**
   - [ ] 访问 `/login`
   - [ ] 使用Tab键导航到SSO按钮
   - [ ] 使用Enter键激活
   - [ ] 验证SSO流程启动

3. **Admin SAML配置**
   - [ ] 访问 `/admin/sso/saml`
   - [ ] 使用Tab键导航表格
   - [ ] 验证所有Action按钮可键盘访问
   - [ ] 使用Enter键打开编辑对话框
   - [ ] 使用Tab在表单字段间导航
   - [ ] 使用Esc键关闭对话框

**预期结果**: ✅ 完全键盘可访问

---

### 测试场景 4.2: 屏幕阅读器

**前置条件**: 启用屏幕阅读器 (NVDA, JAWS, VoiceOver)

**测试步骤**:

1. **Onboarding向导**
   - [ ] 访问 `/onboarding`
   - [ ] 验证标题正确朗读: "首次运行设置"
   - [ ] 验证步骤指示器朗读: "Step 1 of 4"
   - [ ] 验证Provider卡片有描述性label
   - [ ] 验证按钮有清晰label: "下一步", "上一步"

2. **表单字段**
   - [ ] 验证所有输入框有label
   - [ ] 验证错误消息与字段关联
   - [ ] 验证必填字段标记正确

3. **表格**
   - [ ] Admin SAML列表表格有正确的表头
   - [ ] 每行数据正确关联
   - [ ] Action按钮有描述性文本

**预期结果**: ✅ 屏幕阅读器体验良好

---

### 测试场景 4.3: ARIA属性

**前置条件**: 使用浏览器开发者工具

**测试步骤**:

1. **检查ARIA roles**
   - [ ] 对话框有 `role="dialog"` 和 `aria-labelledby`
   - [ ] 按钮有正确的 `aria-label` (如果没有可见文本)
   - [ ] 表单有 `aria-invalid` (当验证失败时)
   - [ ] 加载状态有 `aria-busy="true"`

2. **检查ARIA states**
   - [ ] 选中的Provider有 `aria-selected="true"`
   - [ ] 展开的下拉菜单有 `aria-expanded="true"`
   - [ ] 禁用的按钮有 `aria-disabled="true"`

**预期结果**: ✅ ARIA属性使用正确

---

## 🎯 测试套件 5: 错误处理

### 测试场景 5.1: 网络错误

**测试步骤**:

1. **离线状态**
   - [ ] 打开浏览器开发者工具
   - [ ] 模拟离线 (Network throttling -> Offline)
   - [ ] 尝试提交Onboarding表单
   - [ ] 验证出现友好错误提示
   - [ ] 验证提供重试选项
   - [ ] 恢复在线
   - [ ] 点击重试
   - [ ] 验证操作成功

2. **慢网络**
   - [ ] 模拟慢网络 (Slow 3G)
   - [ ] 提交表单
   - [ ] 验证出现加载指示器
   - [ ] 验证不会超时过早
   - [ ] 验证最终成功

**预期结果**: ✅ 网络问题优雅处理

---

### 测试场景 5.2: API错误

**测试步骤**:

1. **500服务器错误**
   - [ ] 模拟后端返回500错误
   - [ ] 提交表单
   - [ ] 验证出现错误提示: "服务器错误，请稍后重试"
   - [ ] 验证页面不崩溃

2. **400验证错误**
   - [ ] 提交无效数据导致400错误
   - [ ] 验证显示具体字段错误
   - [ ] 验证错误消息清晰可懂

3. **401未授权**
   - [ ] 模拟session过期
   - [ ] 尝试操作
   - [ ] 验证重定向到登录页
   - [ ] 验证显示提示: "会话已过期，请重新登录"

**预期结果**: ✅ API错误正确分类和处理

---

### 测试场景 5.3: 空状态

**测试步骤**:

1. **无SAML Provider**
   - [ ] 清空数据库SAML Provider表
   - [ ] 访问 `/login`
   - [ ] 验证显示: "No SSO providers configured"
   - [ ] 验证提供联系管理员的指引

2. **无Agent**
   - [ ] 清空Agent数据
   - [ ] 访问Agent列表页
   - [ ] 验证显示空状态插画
   - [ ] 验证提供 "创建第一个Agent" 按钮

**预期结果**: ✅ 空状态有友好提示

---

## 🎯 测试套件 6: 兼容性

### 测试场景 6.1: 浏览器兼容性

**测试步骤**:

在以下浏览器中重复关键流程:

- [ ] **Chrome** (最新版)
  - [ ] Onboarding完整流程
  - [ ] SSO登录
  - [ ] Admin SAML CRUD

- [ ] **Firefox** (最新版)
  - [ ] Onboarding完整流程
  - [ ] SSO登录
  - [ ] Admin SAML CRUD

- [ ] **Safari** (最新版)
  - [ ] Onboarding完整流程
  - [ ] SSO登录
  - [ ] Admin SAML CRUD

- [ ] **Edge** (最新版)
  - [ ] Onboarding完整流程
  - [ ] SSO登录
  - [ ] Admin SAML CRUD

**预期结果**: ✅ 所有浏览器功能一致

---

### 测试场景 6.2: 响应式设计

**测试步骤**:

1. **移动设备 (375px)**
   - [ ] 调整浏览器宽度到375px
   - [ ] 验证Onboarding向导响应式布局
   - [ ] 验证按钮不被截断
   - [ ] 验证表单可用

2. **平板设备 (768px)**
   - [ ] 调整宽度到768px
   - [ ] 验证Admin表格响应式
   - [ ] 验证模态对话框适配

3. **桌面 (1920px)**
   - [ ] 验证布局居中
   - [ ] 验证不会过宽

**预期结果**: ✅ 所有尺寸下可用

---

## 📝 测试结果记录

### 测试执行摘要

- **测试日期**: ___________
- **测试人员**: ___________
- **总用例数**: 30+
- **通过数**: ___________
- **失败数**: ___________
- **阻塞数**: ___________

### 发现的问题

| ID | 严重级别 | 描述 | 复现步骤 | 状态 |
|----|---------|------|---------|------|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |

### 测试结论

- [ ] ✅ 通过 - 所有功能正常
- [ ] ⚠️ 有minor问题但可接受
- [ ] ❌ 失败 - 有critical问题需修复

### 签名

测试人员: ___________ 日期: ___________  
审核人员: ___________ 日期: ___________

---

## 🔧 附录: 常见问题排查

### 问题1: Onboarding页面不显示

**检查项**:
- [ ] 数据库连接正常
- [ ] `onboarding_state`表存在
- [ ] Frontend正确连接Backend API
- [ ] 浏览器控制台无错误

### 问题2: SSO按钮点击无反应

**检查项**:
- [ ] SAML Provider已在数据库中配置
- [ ] `entity_id`和`sso_url`配置正确
- [ ] Backend `/api/auth/saml/*/start`端点可访问
- [ ] CORS配置正确

### 问题3: Admin页面403 Forbidden

**检查项**:
- [ ] 用户已登录
- [ ] 用户有admin角色
- [ ] JWT token有效
- [ ] Backend鉴权中间件配置正确

---

**文档版本**: v1.0  
**最后更新**: 2026-06-15
