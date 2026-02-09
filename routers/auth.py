from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

# --- OPTIMIZED SECURE LOGIN PAGE ---
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=no">
  
  <title>Luviio - Secure Access Portal</title>
  <meta name="theme-color" content="#050505">

  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">

  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

  <style>
    /* --- 1. DESIGN TOKENS --- */
    :root { 
        --bg: #050505; --card-bg: rgba(20, 20, 20, 0.6); --border: rgba(255,255,255,0.08); 
        --text: #fff; --text-dim: #a1a1aa; 
        --accent: #3b82f6; --accent-glow: rgba(59, 130, 246, 0.4);
        --success: #22c55e; --error: #ef4444;
    }

    /* --- 2. APP FEEL (NO BLUE FLASH / SELECTION) --- */
    * { 
        box-sizing: border-box; margin: 0; padding: 0; 
        -webkit-tap-highlight-color: transparent; outline: none; 
    }
    
    body { 
        background: var(--bg); color: var(--text); 
        font-family: 'Plus Jakarta Sans', sans-serif; 
        height: 100dvh; width: 100vw; overflow: hidden; 
        display: flex; flex-direction: column;
        user-select: none; -webkit-user-select: none; /* App Like */
    }

    input { user-select: text; -webkit-user-select: text; } /* Typing allowed */

    /* GRID BACKGROUND */
    .grid-bg { 
        position: absolute; inset: 0; z-index: -1; 
        background-image: linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px); 
        background-size: 80px 80px; opacity: 0.12; 
        mask-image: radial-gradient(circle at center, black 40%, transparent 80%); 
        pointer-events: none;
    }

    /* --- 3. LAYOUT (HEADER / FOOTER) --- */
    nav {
        width: 100%; padding: 20px 30px; 
        display: flex; justify-content: space-between; align-items: center;
        z-index: 10;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.2rem; color: white; text-decoration: none; letter-spacing: -0.02em; }
    .brand img { height: 24px; width: auto; }
    
    .nav-link { color: var(--text-dim); text-decoration: none; font-size: 0.9rem; font-weight: 600; transition: 0.3s; }
    .nav-link:hover { color: white; }

    main {
        flex: 1; display: flex; justify-content: center; align-items: center;
        padding: 20px; z-index: 5;
    }

    footer {
        width: 100%; padding: 20px; text-align: center; 
        color: #444; font-size: 0.75rem; font-weight: 500; z-index: 10;
    }

    /* --- 4. AUTH CARD (GLASSMORPHISM) --- */
    .auth-card { 
        width: 100%; max-width: 420px; padding: 40px; 
        background: var(--card-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border); border-radius: 24px; 
        box-shadow: 0 20px 60px rgba(0,0,0,0.5); 
        position: relative; opacity: 0; transform: translateY(20px);
    }

    .header-text { text-align: center; margin-bottom: 30px; } 
    .title { font-size: 1.5rem; font-weight: 700; margin-bottom: 6px; letter-spacing: -0.02em; } 
    .subtitle { color: var(--text-dim); font-size: 0.9rem; }

    /* SOCIAL BUTTONS */
    .social-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 25px; }
    .btn-social { 
        display: flex; align-items: center; justify-content: center; gap: 10px; padding: 12px; 
        background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; 
        color: white; cursor: pointer; transition: all 0.2s; font-size: 0.9rem; font-weight: 600;
    }
    .btn-social:hover { background: rgba(255,255,255,0.08); border-color: #555; transform: translateY(-2px); }
    .btn-social i { font-size: 1.1rem; }

    .divider { display: flex; align-items: center; margin-bottom: 25px; color: var(--text-dim); font-size: 0.75rem; font-weight: 600; letter-spacing: 1px; } 
    .divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: var(--border); opacity: 0.5; } 
    .divider span { padding: 0 15px; }

    /* INPUTS */
    .input-group { margin-bottom: 16px; position: relative; } 
    .input-wrapper { position: relative; }
    .input-icon { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: var(--text-dim); font-size: 1.1rem; pointer-events: none; transition: 0.3s; }
    
    input { 
        width: 100%; padding: 16px 16px 16px 48px; 
        background: rgba(0,0,0,0.3); border: 1px solid var(--border); 
        border-radius: 14px; color: white; font-size: 1rem; outline: none; transition: 0.3s; 
    }
    input:focus { border-color: var(--accent); background: rgba(0,0,0,0.5); box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1); }
    input:focus + .input-icon { color: white; }

    /* HONEYPOT */
    .hp-field { display: none; }

    /* MAIN BUTTON */
    .btn-primary { 
        width: 100%; padding: 16px; background: white; color: black; 
        border: none; border-radius: 100px; font-weight: 700; font-size: 1rem; cursor: pointer; margin-top: 10px; 
        transition: transform 0.2s, box-shadow 0.2s; position: relative; overflow: hidden;
        display: flex; justify-content: center; align-items: center;
    }
    .btn-primary:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(255,255,255,0.15); }
    .btn-primary:active:not(:disabled) { transform: scale(0.98); } 
    .btn-primary:disabled { opacity: 0.6; cursor: wait; }

    .loader { display: none; width: 20px; height: 20px; border: 2px solid rgba(0,0,0,0.1); border-top-color: #000; border-radius: 50%; animation: spin 0.8s linear infinite; } 
    @keyframes spin { to { transform: rotate(360deg); } }

    /* FOOTER LINKS */
    .toggle-text { margin-top: 24px; text-align: center; font-size: 0.9rem; color: var(--text-dim); } 
    .link { color: white; text-decoration: none; font-weight: 600; cursor: pointer; margin-left: 5px; transition: color 0.2s; }
    .link:hover { color: var(--accent); }

    /* TOAST */
    .toast {
        position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%) translateY(20px);
        background: rgba(20, 20, 20, 0.95); border: 1px solid var(--border);
        padding: 12px 24px; border-radius: 50px; display: flex; align-items: center; gap: 10px;
        box-shadow: 0 20px 50px rgba(0,0,0,0.6); font-size: 0.9rem; color: #fff; z-index: 100;
        opacity: 0; pointer-events: none; backdrop-filter: blur(10px); transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .toast.visible { opacity: 1; transform: translateX(-50%) translateY(0); }
    .toast.error i { color: var(--error); }
    .toast.success i { color: var(--success); }
  </style>
</head>
<body>

  <div class="grid-bg"></div>

  <nav>
    <a href="/" class="brand">
      <img src="/images/logo.png" alt="Logo" onerror="this.style.display='none'">
      <span>LUVIIO</span>
    </a>
    <a href="mailto:contact@luviio.in" class="nav-link">Contact</a>
  </nav>

  <main>
    <div class="auth-card" id="authCard">
      <div class="header-text">
        <div class="title" id="formTitle">Welcome Back</div>
        <div class="subtitle" id="formSubtitle">Secure access to your dashboard</div>
      </div>

      <div class="social-grid">
        <button class="btn-social" onclick="signInWithProvider('google')">
          <i class="ri-google-fill"></i> Google
        </button>
        <button class="btn-social" onclick="signInWithProvider('github')">
          <i class="ri-github-fill"></i> GitHub
        </button>
      </div>

      <div class="divider"><span>OR EMAIL</span></div>

      <form id="authForm" onsubmit="handleAuth(event)">
        <input type="text" id="_hp_check" class="hp-field" tabindex="-1" autocomplete="off">
        
        <div class="input-group">
          <div class="input-wrapper">
            <input type="email" id="email" placeholder="name@company.com" required autocomplete="email">
            <i class="ri-mail-line input-icon"></i>
          </div>
        </div>
        
        <div class="input-group">
          <div class="input-wrapper">
            <input type="password" id="password" placeholder="Password" required autocomplete="current-password">
            <i class="ri-lock-2-line input-icon"></i>
          </div>
        </div>

        <button type="submit" class="btn-primary" id="authBtn">
          <span id="btnText">Sign In</span>
          <div class="loader" id="btnLoader"></div>
        </button>

        <div class="toggle-text">
          <span id="footerPrompt">New here?</span>
          <span class="link" onclick="toggleMode()" id="toggleLink">Create account</span>
        </div>
      </form>
    </div>
  </main>

  <footer>
    &copy; 2026 Luviio Technologies. Secure & Verified.
  </footer>

  <div id="toast" class="toast">
    <i class="ri-information-fill"></i>
    <span id="toastMsg">Notification</span>
  </div>

  <script>
    // --- CONFIGURATION ---
    const SB_URL = 'https://enqcujmzxtrbfkaungpm.supabase.co';
    const SB_KEY = 'sb_publishable_0jeCSzd3NkL-RlQn8X-eTA_-xH03xVd';
    
    let supabaseClient = null;
    let isSignUp = false;
    let isProcessing = false;

    document.addEventListener("DOMContentLoaded", () => {
        // Init Supabase
        if(typeof supabase !== 'undefined') {
            supabaseClient = supabase.createClient(SB_URL, SB_KEY);
        }
        
        // GSAP Animation
        if(typeof gsap !== 'undefined') {
            gsap.to("#authCard", { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" });
        } else {
            document.getElementById('authCard').style.opacity = 1;
            document.getElementById('authCard').style.transform = "translateY(0)";
        }
    });

    // --- AUTH LOGIC ---
    async function signInWithProvider(providerName) {
      if(!supabaseClient) return;
      try {
        const { data, error } = await supabaseClient.auth.signInWithOAuth({
          provider: providerName,
          options: { redirectTo: window.location.origin + '/onboarding' }
        });
        if (error) throw error;
      } catch (error) { showToast("Connection Error", "error"); }
    }

    function toggleMode() {
      isSignUp = !isSignUp;
      const title = isSignUp ? "Create Account" : "Welcome Back";
      const sub = isSignUp ? "Start your verified journey" : "Secure access to your dashboard";
      const btn = isSignUp ? "Sign Up" : "Sign In";
      const prompt = isSignUp ? "Already a member?" : "New here?";
      const link = isSignUp ? "Log in" : "Create account";

      // Animation
      if(typeof gsap !== 'undefined') {
          gsap.fromTo(".header-text", {opacity:0, y:-5}, {opacity:1, y:0, duration:0.3});
      }

      document.getElementById('formTitle').innerText = title;
      document.getElementById('formSubtitle').innerText = sub;
      document.getElementById('btnText').innerText = btn;
      document.getElementById('footerPrompt').innerText = prompt;
      document.getElementById('toggleLink').innerText = link;
    }

    async function handleAuth(e) {
      e.preventDefault();
      if (isProcessing) return;
      if (document.getElementById('_hp_check').value) return; // Honeypot
      
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;

      if (password.length < 6) { 
          showToast("Password too short (min 6 chars)", "error"); 
          shakeCard(); return; 
      }
      
      setLoading(true);

      try {
        if(!supabaseClient) throw new Error("Connection failed.");

        let result;
        if (isSignUp) {
          result = await supabaseClient.auth.signUp({ 
            email, password, options: { emailRedirectTo: window.location.origin + '/onboarding' }
          });
        } else {
          result = await supabaseClient.auth.signInWithPassword({ email, password });
        }

        if (result.error) throw result.error;

        if (isSignUp && result.data.user && !result.data.session) {
           showToast("Check your email for confirmation link.", "success");
           document.getElementById('authForm').reset();
        } else {
           showToast("Access Granted", "success");
           // Redirect Logic
           checkProfileAndRedirect(result.data.user.id);
        }

      } catch (error) {
        let msg = error.message;
        if(msg.includes("Invalid login")) msg = "Incorrect email or password.";
        showToast(msg, "error");
        shakeCard();
      } finally { 
        setLoading(false); 
      }
    }

    async function checkProfileAndRedirect(userId) {
        try {
            const { data: profile } = await supabaseClient.from('profiles').select('role').eq('id', userId).single();
            if (profile && profile.role) {
                setTimeout(() => window.location.href = "/dashboard", 800);
            } else {
                setTimeout(() => window.location.href = "/onboarding", 800);
            }
        } catch (err) {
            setTimeout(() => window.location.href = "/onboarding", 800);
        }
    }

    // --- UI HELPERS ---
    function setLoading(state) {
      isProcessing = state;
      document.getElementById('btnText').style.display = state ? 'none' : 'block';
      document.getElementById('btnLoader').style.display = state ? 'block' : 'none';
      document.getElementById('authBtn').disabled = state;
    }

    function showToast(msg, type) {
      const toast = document.getElementById('toast');
      const icon = toast.querySelector('i');
      document.getElementById('toastMsg').innerText = msg;
      toast.className = `toast visible ${type}`;
      icon.className = type === 'error' ? "ri-error-warning-fill" : "ri-checkbox-circle-fill";
      setTimeout(() => toast.className = "toast", 3000);
    }

    function shakeCard() {
        if(typeof gsap !== 'undefined') {
            gsap.to(".auth-card", { x: -6, duration: 0.08, repeat: 3, yoyo: true });
        }
    }
  </script>
</body>
</html>
"""

@router.get("/", response_class=HTMLResponse)
async def get_login_page():
    return LOGIN_HTML