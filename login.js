const puppeteer = require('puppeteer');
const axios = require('axios');

// ===================== Telegram 通知函数 =====================
async function sendTelegramMessage(botToken, chatId, message, screenshotPath = null) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  
  try {
    await axios.post(url, {
      chat_id: chatId,
      text: message,
      parse_mode: 'Markdown'
    });
    console.log('✅ Telegram 通知发送成功');
  } catch (error) {
    console.error('❌ Telegram 通知失败:', error.message);
  }
}

// ===================== 核心：模拟点击处理 Turnstile =====================
async function solveTurnstileDirectly(page) {
  console.log('🔄 准备处理 Turnstile 验证...');
  
  try {
    // 1. 等待验证组件加载
    await page.waitForSelector('div.g-recaptcha', { timeout: 15000 });
    console.log('✅ 找到验证组件');
    
    // 2. 执行偏移点击模拟人类操作
    console.log('🖱️ 执行模拟点击...');
    const clickResult = await page.evaluate(() => {
      const container = document.querySelector('div.g-recaptcha');
      if (!container) return { success: false, reason: '未找到验证容器' };
      
      const rect = container.getBoundingClientRect();
      
      // 计算点击位置：容器中心向左偏移120像素
      const clickX = rect.left + rect.width / 2 - 120;
      const clickY = rect.top + rect.height / 2;
      
      // 创建并触发鼠标事件序列
      const events = ['mousedown', 'mouseup', 'click'];
      events.forEach(eventType => {
        const event = new MouseEvent(eventType, {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: clickX,
          clientY: clickY
        });
        container.dispatchEvent(event);
      });
      
      return { 
        success: true, 
        clickX: Math.round(clickX), 
        clickY: Math.round(clickY),
        containerSize: { width: rect.width, height: rect.height }
      };
    });
    
    if (!clickResult.success) {
      throw new Error(clickResult.reason);
    }
    
    console.log(`✅ 模拟点击完成 (X: ${clickResult.clickX}, Y: ${clickResult.clickY})`);
    
    // 3. 轮询检查令牌生成（最多等待25秒）
    console.log('⏳ 等待验证令牌生成...');
    let token = null;
    
    for (let attempt = 1; attempt <= 25; attempt++) {
      // 使用 page.waitFor 替代 page.waitForTimeout（兼容旧版）
      await page.waitFor(1000);
      
      token = await page.evaluate(() => {
        // 直接查找 cf-turnstile-response 输入框
        const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
        if (cfInput && cfInput.value && cfInput.value.length > 20) {
          return cfInput.value;
        }
        return null;
      });
      
      if (token) {
        console.log(`✅ Turnstile 令牌获取成功 (第${attempt}秒)`);
        console.log(`  令牌预览: ${token.substring(0, 30)}...`);
        
        // 确保 g-recaptcha-response 字段也有值
        await page.evaluate((tokenValue) => {
          const gInput = document.querySelector('input[name="g-recaptcha-response"]');
          if (gInput) {
            gInput.value = tokenValue;
          }
        }, token);
        
        break;
      }
      
      if (attempt % 5 === 0) {
        console.log(`  仍在等待验证... (已等待 ${attempt} 秒)`);
      }
    }
    
    if (!token) {
      // 最终检查
      const finalCheck = await page.evaluate(() => {
        const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
        return {
          exists: !!cfInput,
          valueLength: cfInput ? cfInput.value.length : 0
        };
      });
      
      throw new Error(`验证超时。输入框存在: ${finalCheck.exists}, 值长度: ${finalCheck.valueLength}`);
    }
    
    return true;
    
  } catch (error) {
    console.error('❌ Turnstile 处理失败:', error.message);
    throw error;
  }
}

// ===================== 主登录函数 =====================
async function login() {
  // 环境变量检查
  const requiredEnvVars = ['WEBSITE_URL', 'USERNAME', 'PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'];
  const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
  
  if (missingVars.length > 0) {
    console.error('❌ 缺少必要的环境变量:', missingVars.join(', '));
    console.log('💡 请确保 .env 文件包含以下变量:');
    console.log('   WEBSITE_URL, USERNAME, PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID');
    process.exit(1);
  }
  
  console.log('🚀 开始登录流程...');
  console.log(`🌐 目标网站: ${process.env.WEBSITE_URL}`);
  console.log(`👤 登录账号: ${process.env.USERNAME.replace(/(.{2}).*(@.*)/, '$1***$2')}`);
  
  const browser = await puppeteer.launch({
    headless: process.env.HEADLESS !== 'false',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--window-size=1280,720',
      '--disable-blink-features=AutomationControlled'
    ],
    defaultViewport: { width: 1280, height: 720 }
  });
  
  const page = await browser.newPage();
  
  // 设置更真实的浏览器指纹
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });
  
  let success = false;
  let finalMessage = '';
  
  try {
    // 1. 访问登录页面
    console.log('\n📄 加载登录页面...');
    await page.goto(process.env.WEBSITE_URL, { 
      waitUntil: 'networkidle2',
      timeout: 30000
    });
    
    // 截图记录初始页面
    await page.screenshot({ path: '01-initial-page.png' });
    
    // 2. 填写登录表单
    console.log('📝 填写登录信息...');
    
    // 查找并填写邮箱
    const emailSelectors = ['input[name="email"]', 'input[type="email"]', '#email'];
    await page.waitForSelector(emailSelectors.join(','), { timeout: 10000 });
    
    // 模拟人类输入速度
    await page.type(emailSelectors.join(','), process.env.USERNAME, { delay: 50 + Math.random() * 50 });
    console.log('✅ 邮箱填写完成');
    
    // 查找并填写密码
    const passwordSelectors = ['input[name="password"]', 'input[type="password"]', '#password'];
    await page.type(passwordSelectors.join(','), process.env.PASSWORD, { delay: 50 + Math.random() * 50 });
    console.log('✅ 密码填写完成');
    
    await page.screenshot({ path: '02-form-filled.png' });
    
    // 3. 处理Cloudflare Turnstile验证
    console.log('\n🔐 处理验证码...');
    await solveTurnstileDirectly(page);
    
    await page.screenshot({ path: '03-after-verification.png' });
    
    // 4. 点击登录按钮
    console.log('\n🚀 提交登录表单...');
    
    // 方法1: 直接点击提交按钮
    await page.evaluate(() => {
      const submitBtn = document.querySelector('button.submit-btn, button[type="submit"]');
      if (submitBtn) {
        submitBtn.click();
        return true;
      }
      return false;
    });
    
    // 等待页面跳转或变化
    console.log('⏳ 等待登录响应...');
    // 使用 page.waitFor 替代 page.waitForTimeout
    await page.waitFor(3000);
    
    // 尝试检测导航
    try {
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 });
    } catch (e) {
      console.log('⚠️  页面导航超时，可能已停留在当前页');
    }
    
    // 5. 验证登录结果
    console.log('\n📊 验证登录结果...');
    const currentUrl = page.url();
    const pageTitle = await page.title();
    
    console.log(`   当前URL: ${currentUrl}`);
    console.log(`   页面标题: ${pageTitle}`);
    
    await page.screenshot({ path: '04-final-page.png' });
    
    // 判断登录成功条件
    const isLoginPage = currentUrl.includes('/login') || 
                       pageTitle.toLowerCase().includes('sign in') ||
                       pageTitle.toLowerCase().includes('login');
    
    if (!isLoginPage) {
      success = true;
      finalMessage = `*✅ 登录成功！*\n\n` +
                    `⏰ 时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                    `👤 账号: ${process.env.USERNAME}\n` +
                    `🌐 当前页面: ${currentUrl}\n` +
                    `📝 页面标题: ${pageTitle}\n` +
                    `\n✅ 自动化流程执行完毕`;
      
      console.log('🎉 登录成功！');
    } else {
      // 检查是否有错误信息
      const errorText = await page.evaluate(() => {
        const errorDiv = document.querySelector('.error, .alert-danger, .text-red-500, [class*="error"], [class*="alert"]');
        return errorDiv ? errorDiv.textContent.trim() : '无明确错误信息';
      });
      
      finalMessage = `*⚠️  登录可能失败*\n\n` +
                    `⏰ 时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                    `👤 账号: ${process.env.USERNAME}\n` +
                    `🌐 仍停留在: ${currentUrl}\n` +
                    `📝 页面标题: ${pageTitle}\n` +
                    `❌ 错误信息: ${errorText.substring(0, 100)}`;
      
      console.log('⚠️  可能登录失败，当前仍在登录页面');
    }
    
  } catch (error) {
    console.error('\n❌ 登录过程中发生错误:', error.message);
    
    // 错误时截图
    await page.screenshot({ 
      path: '05-error-occurred.png',
      fullPage: true 
    });
    
    finalMessage = `*❌ 登录失败！*\n\n` +
                  `⏰ 时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}\n` +
                  `👤 账号: ${process.env.USERNAME}\n` +
                  `❌ 错误类型: ${error.name}\n` +
                  `📝 错误详情: ${error.message}\n` +
                  `\n🔍 请查看错误截图: 05-error-occurred.png`;
    
  } finally {
    // 发送Telegram通知
    await sendTelegramMessage(
      process.env.TELEGRAM_BOT_TOKEN, 
      process.env.TELEGRAM_CHAT_ID, 
      finalMessage
    );
    
    // 关闭浏览器
    await browser.close();
    console.log('\n🔄 浏览器已关闭');
    
    // 清理截图文件（可选）
    if (success) {
      const fs = require('fs');
      const files = ['01-initial-page.png', '02-form-filled.png', '03-after-verification.png', '04-final-page.png'];
      files.forEach(file => {
        if (fs.existsSync(file)) fs.unlinkSync(file);
      });
      console.log('🧹 临时截图已清理');
    }
    
    console.log(`\n${success ? '✅' : '❌'} 脚本执行完成`);
    process.exit(success ? 0 : 1);
  }
}

// ===================== 脚本执行 =====================
// 检查是否直接运行此脚本
if (require.main === module) {
  console.log(`
==========================================
    Betadash.lunes.host 自动化登录脚本
==========================================
  `);
  
  // 加载环境变量
  require('dotenv').config();
  
  login().catch(error => {
    console.error('💥 脚本执行失败:', error);
    process.exit(1);
  });
}

module.exports = { login };