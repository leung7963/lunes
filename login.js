const puppeteer = require('puppeteer');
const axios = require('axios');

// ===================== Telegram 通知函数 (保持不变) =====================
async function sendTelegramMessage(botToken, chatId, message) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  await axios.post(url, {
    chat_id: chatId,
    text: message,
    parse_mode: 'Markdown'
  }).catch(error => {
    console.error('Telegram 通知失败:', error.message);
  });
}

// ===================== 核心修改：模拟点击处理Turnstile =====================
async function solveTurnstileDirectly(page) {
  console.log('🔄 尝试通过模拟点击处理 Cloudflare Turnstile...');

  // 1. 等待并定位Turnstile验证容器
  // 注意：选择器可能需要根据实际页面调整，例如 '.cf-turnstile' 或 iframe
  try {
    await page.waitForSelector('[class*="turnstile"], iframe[src*="challenges.cloudflare.com"]', { timeout: 10000 });
  } catch (e) {
    console.log('⚠️  未找到明确的Turnstile容器，尝试直接查找cf-turnstile-response输入框');
  }

  // 2. 模拟人类点击（关键步骤）
  // 在验证容器区域内，随机偏移点击，模拟人类不精确操作
  await page.evaluate(() => {
    const container = document.querySelector('.cf-turnstile') || document.querySelector('iframe[src*="challenges.cloudflare.com"]')?.parentElement;
    if (container) {
      const rect = container.getBoundingClientRect();
      // 计算容器中心点
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      
      // 生成随机偏移量（例如 -80 到 80 像素之间），模拟人类点击偏差
      const offsetX = centerX + (Math.random() * 160 - 80);
      const offsetY = centerY + (Math.random() * 160 - 80);
      
      // 创建并触发鼠标事件
      const mouseDownEvent = new MouseEvent('mousedown', {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: offsetX,
        clientY: offsetY
      });
      container.dispatchEvent(mouseDownEvent);
      
      const mouseUpEvent = new MouseEvent('mouseup', {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: offsetX,
        clientY: offsetY
      });
      container.dispatchEvent(mouseUpEvent);
      
      const clickEvent = new MouseEvent('click', {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: offsetX,
        clientY: offsetY
      });
      container.dispatchEvent(clickEvent);
      
      console.log('🖱️  已在坐标(' + Math.round(offsetX) + ',' + Math.round(offsetY) + ')执行模拟点击');
      return true;
    }
    return false;
  });

  console.log('⏳ 等待验证令牌生成...');

  // 3. 轮询检查令牌是否已生成（关键步骤）
  let token = null;
  for (let i = 0; i < 20; i++) { // 最多等待20秒
    token = await page.evaluate(() => {
      // 尝试从隐藏的textarea获取令牌
      const textarea = document.querySelector('textarea[name="cf-turnstile-response"]');
      if (textarea && textarea.value && textarea.value.length > 10) {
        return textarea.value;
      }
      // 某些网站可能将令牌存储在input或其他元素中
      const input = document.querySelector('input[name="cf-turnstile-response"]');
      if (input && input.value && input.value.length > 10) {
        return input.value;
      }
      return null;
    });

    if (token) {
      console.log('✅ Turnstile 令牌已获取');
      break;
    }

    // 等待1秒后再次检查
    await page.waitForTimeout(1000);
  }

  if (!token) {
    // 如果页面有挑战，尝试自动处理
    const hasChallenge = await page.evaluate(() => {
      return document.querySelector('#challenge-running') !== null || 
             document.querySelector('.challenge-form') !== null;
    });
    
    if (hasChallenge) {
      console.log('⚠️  检测到交互式挑战，尝试自动处理...');
      // 这里可以添加处理简单挑战的逻辑
    }
    
    throw new Error('未能获取Turnstile令牌，验证可能未通过');
  }

  return true;
}

// ===================== 主登录函数 =====================
async function login() {
  const browser = await puppeteer.launch({
    headless: process.env.HEADLESS !== 'false', // 默认无头，可设置HEADLESS=false显示浏览器
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--window-size=1280,720'
    ]
  });
  const page = await browser.newPage();

  // 设置更真实的User-Agent
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  try {
    // 1. 访问登录页面
    console.log(`🌐 访问登录页面: ${process.env.WEBSITE_URL}`);
    await page.goto(process.env.WEBSITE_URL, { 
      waitUntil: 'networkidle2',
      timeout: 30000 
    });

    // 2. 输入凭据（根据实际页面调整选择器）
    console.log('📝 填写登录信息...');
    // 邮箱输入 - 根据之前页面分析，可能是 input[name="email"] 或 #email
    await page.waitForSelector('input[name="email"], #email, input[type="email"]', { timeout: 10000 });
    await page.type('input[name="email"], #email, input[type="email"]', process.env.USERNAME, { delay: 50 }); // 模拟人工输入速度

    // 密码输入 - 可能是 input[name="password"] 或 #password
    await page.type('input[name="password"], #password, input[type="password"]', process.env.PASSWORD, { delay: 50 });

    // 3. 处理Cloudflare Turnstile验证
    await solveTurnstileDirectly(page);

    // 4. 提交登录表单
    console.log('🚀 提交登录表单...');
    // 登录按钮文字可能是 "Continue to dashboard" 或 "Sign in"
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
      const targetBtn = buttons.find(btn => 
        btn.textContent.includes('Continue') || 
        btn.textContent.includes('Sign in') ||
        btn.textContent.includes('Login') ||
        btn.value === 'Continue'
      );
      if (targetBtn) {
        targetBtn.click();
        return true;
      }
      // 如果没有找到，点击第一个提交按钮
      const submitBtn = document.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn) submitBtn.click();
      return false;
    });

    // 5. 等待登录完成
    console.log('⏳ 等待登录跳转...');
    await page.waitForNavigation({ 
      waitUntil: 'networkidle2', 
      timeout: 15000 
    }).catch(() => {
      console.log('⚠️  导航超时，但可能已登录成功');
    });

    // 6. 验证登录结果
    const currentUrl = page.url();
    const pageTitle = await page.title();
    
    console.log(`📊 登录结果检查:
      当前URL: ${currentUrl}
      页面标题: ${pageTitle}`);

    // 登录成功判断：URL不再包含login且标题不是登录页
    if (!currentUrl.includes('/login') && !pageTitle.toLowerCase().includes('sign in') && !pageTitle.toLowerCase().includes('login')) {
      const successMessage = `*✅ 登录成功！*\n\n` +
                            `时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                            `账号: ${process.env.USERNAME}\n` +
                            `页面: ${currentUrl}\n` +
                            `标题: ${pageTitle}`;
      
      await sendTelegramMessage(process.env.TELEGRAM_BOT_TOKEN, process.env.TELEGRAM_CHAT_ID, successMessage);
      console.log('✅ 登录成功！Telegram通知已发送。');
      
      // 可选：截取成功页面
      await page.screenshot({ path: 'login-success.png', fullPage: false });
    } else {
      // 可能登录失败
      await page.screenshot({ path: 'login-ambiguous.png', fullPage: true });
      const warningMessage = `*⚠️  登录状态待确认*\n\n` +
                            `时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                            `账号: ${process.env.USERNAME}\n` +
                            `当前仍在登录相关页面\n` +
                            `URL: ${currentUrl}\n` +
                            `标题: ${pageTitle}`;
      await sendTelegramMessage(process.env.TELEGRAM_BOT_TOKEN, process.env.TELEGRAM_CHAT_ID, warningMessage);
      console.log('⚠️  登录状态不明确，已发送警告通知');
    }

  } catch (error) {
    // 错误处理
    console.error('❌ 登录失败：', error.message);
    
    // 截取失败页面
    await page.screenshot({ 
      path: 'login-failure.png', 
      fullPage: true 
    });
    
    // 发送错误通知
    const errorMessage = `*❌ 登录失败！*\n\n` +
                        `时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                        `账号: ${process.env.USERNAME}\n` +
                        `错误: ${error.message}\n` +
                        `截图已保存: login-failure.png`;
    
    await sendTelegramMessage(process.env.TELEGRAM_BOT_TOKEN, process.env.TELEGRAM_CHAT_ID, errorMessage);
    
    throw error;
  } finally {
    // 关闭浏览器
    await browser.close();
    console.log('🔄 浏览器已关闭');
  }
}

// 启动登录流程
login().catch(error => {
  console.error('脚本执行失败:', error);
  process.exit(1);
});