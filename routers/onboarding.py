from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

ONBOARDING_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=no">
  <title>Setup Profile - Luviio</title>

  <link rel="preconnect" href="https://enqcujmzxtrbfkaungpm.supabase.co" crossorigin>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://cdn.jsdelivr.net">
  <link rel="prefetch" href="/dashboard">

  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">
  
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

  <style>
    /* CORE VARIABLES */
    :root { 
      --bg: #050505; --card-bg: rgba(20, 20, 20, 0.6); --border: rgba(255,255,255,0.08); 
      --text: #fff; --text-dim: #a1a1aa; 
      --accent: #3b82f6; --accent-glow: rgba(59, 130, 246, 0.4);
    }
    
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; outline: none; }
    
    body { 
      background: var(--bg); color: var(--text); 
      font-family: 'Plus Jakarta Sans', sans-serif; 
      height: 100dvh; width: 100vw; overflow: hidden; 
      display: flex; flex-direction: column;
      user-select: none;
    }

    /* CRITICAL LOADER CSS */
    #auth-loader {
        position: fixed; inset: 0; background: #050505; z-index: 9999;
        display: flex; flex-direction: column; justify-content: center; align-items: center;
        transition: opacity 0.4s ease-out;
    }
    .spinner { 
        width: 40px; height: 40px; 
        border: 3px solid rgba(255,255,255,0.1); border-top-color: var(--accent); 
        border-radius: 50%; animation: spin 0.6s linear infinite; 
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    
    .status-msg { margin-top: 15px; font-size: 0.8rem; color: #666; letter-spacing: 1px; font-weight: 600; }

    /* LAYOUT & WIZARD STYLES */
    .grid-bg { position: absolute; inset: 0; z-index: -1; opacity: 0.12; background-image: linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px); background-size: 80px 80px; mask-image: radial-gradient(circle at center, black 40%, transparent 80%); }
    
    nav { width: 100%; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; z-index: 10; }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.2rem; color: white; text-decoration: none; }
    .brand img { height: 24px; }
    
    main { flex: 1; display: flex; justify-content: center; align-items: center; padding: 20px; z-index: 5; }
    
    .wizard-wrapper { width: 100%; max-width: 480px; position: relative; display: none; }
    
    .step-card {
      background: var(--card-bg); border: 1px solid var(--border);
      backdrop-filter: blur(20px); border-radius: 24px; padding: 40px 30px;
      position: absolute; top: 0; left: 0; width: 100%;
      opacity: 0; visibility: hidden; transform: translateX(20px);
    }
    .step-card.active { position: relative; opacity: 1; visibility: visible; transform: translateX(0); }

    .progress-track { width: 100%; height: 4px; background: rgba(255,255,255,0.05); border-radius: 10px; margin-bottom: 30px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--accent); width: 20%; transition: width 0.5s cubic-bezier(0.25, 1, 0.5, 1); box-shadow: 0 0 10px var(--accent-glow); }
    
    h2 { font-size: 1.5rem; margin-bottom: 8px; }
    .label { display: block; font-size: 0.9rem; color: var(--text-dim); margin-bottom: 24px; }
    
    input, select, textarea { width: 100%; padding: 16px; background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 14px; color: white; font-size: 1rem; outline: none; margin-bottom: 15px; user-select: text; }
    input:focus { border-color: var(--accent); background: rgba(0,0,0,0.5); }
    
    .radio-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 25px; }
    .radio-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 16px; padding: 20px; cursor: pointer; text-align: center; transition: 0.2s; }
    .radio-card.selected { background: rgba(59, 130, 246, 0.1); border-color: var(--accent); }
    .radio-icon { font-size: 1.5rem; margin-bottom: 8px; color: var(--text-dim); }
    .selected .radio-icon { color: var(--accent); }

    .actions { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }
    .btn-next { background: white; color: black; border: none; padding: 14px 32px; border-radius: 100px; font-weight: 700; cursor: pointer; opacity: 0.3; pointer-events: none; transition: 0.3s; }
    .btn-next.enabled { opacity: 1; pointer-events: all; }
    .btn-back { color: var(--text-dim); cursor: pointer; font-size: 0.9rem; padding: 10px; }
    
    footer { padding: 20px; text-align: center; color: #444; font-size: 0.75rem; }
  </style>
</head>
<body>

  <div id="auth-loader">
    <div class="spinner"></div>
    <div class="status-msg" id="status-text">CONNECTING...</div>
  </div>

  <div class="grid-bg"></div>

  <nav>
    <a href="/" class="brand">
      <img src="/images/logo.png" alt="Logo" onerror="this.style.display='none'"> 
      <span>LUVIIO</span>
    </a>
    <div style="color:#666; font-size:0.8rem; cursor:pointer;" onclick="hardReset()">Sign Out</div>
  </nav>

  <main>
    <div class="wizard-wrapper" id="wizard">
      
      <div class="step-card active" id="step1">
        <div class="progress-track"><div class="progress-fill" style="width: 20%"></div></div>
        <h2>Who are you?</h2>
        <span class="label">Official name for your verified profile.</span>
        <input type="text" id="fullName" placeholder="e.g. Rahul Sharma" oninput="validate(1)">
        <div class="actions" style="justify-content: flex-end;">
          <button class="btn-next" id="btn1" onclick="nextStep(2)">Continue</button>
        </div>
      </div>

      <div class="step-card" id="step2">
        <div class="progress-track"><div class="progress-fill" style="width: 40%"></div></div>
        <h2>Your Purpose?</h2>
        <span class="label">Choose your primary role.</span>
        <div class="radio-grid">
          <div class="radio-card" onclick="selectRole('buyer', this)">
            <div class="radio-icon"><i class="ri-shopping-bag-3-line"></i></div>
            <span>Buyer / User</span>
          </div>
          <div class="radio-card" onclick="selectRole('seller', this)">
            <div class="radio-icon"><i class="ri-store-2-line"></i></div>
            <span>Seller / Merchant</span>
          </div>
        </div>
        <div class="actions">
          <div class="btn-back" onclick="prevStep(1)">Back</div>
          <button class="btn-next" id="btn2" onclick="nextStep(3)">Continue</button>
        </div>
      </div>

      <div class="step-card" id="step3">
        <div class="progress-track"><div class="progress-fill" style="width: 60%"></div></div>
        <h2>Discovery?</h2>
        <span class="label">How did you find Luviio?</span>
        <select id="source" onchange="validate(3)">
          <option value="" disabled selected>Select Option</option>
          <option value="social">Social Media</option>
          <option value="search">Search Engine</option>
          <option value="referral">Friend / Referral</option>
        </select>
        <div class="actions">
          <div class="btn-back" onclick="prevStep(2)">Back</div>
          <button class="btn-next" id="btn3" onclick="handleSourceNext()">Continue</button>
        </div>
      </div>

      <div class="step-card" id="step4">
        <div class="progress-track"><div class="progress-fill" style="width: 80%"></div></div>
        <h2>Store Entity</h2>
        <span class="label">Your business details.</span>
        <input type="text" id="storeName" placeholder="Store Name" oninput="validate(4)">
        <input type="text" id="storeAddress" placeholder="Business Address" oninput="validate(4)">
        <div class="actions">
          <div class="btn-back" onclick="prevStep(3)">Back</div>
          <button class="btn-next" id="btn4" onclick="nextStep(5)">Continue</button>
        </div>
      </div>

      <div class="step-card" id="step5">
        <div class="progress-track"><div class="progress-fill" style="width: 100%"></div></div>
        <h2>Contact & Category</h2>
        <span class="label">How customers reach you.</span>
        <input type="text" id="storeContact" placeholder="Phone or Email" oninput="validate(5)">
        <select id="category" onchange="validate(5)">
          <option value="" disabled selected>Select Category</option>
          <option value="retail">Retail</option>
          <option value="service">Services</option>
          <option value="digital">Digital Goods</option>
        </select>
        <div class="actions">
          <div class="btn-back" onclick="prevStep(4)">Back</div>
          <button class="btn-next" id="btn5" onclick="submitData()">Complete Setup</button>
        </div>
      </div>

    </div>
  </main>

  <footer>&copy; 2026 Luviio. Secure.</footer>

  <script>
    // --- CONFIGURATION ---
    const SB_URL = 'https://enqcujmzxtrbfkaungpm.supabase.co';
    const SB_KEY = 'sb_publishable_0jeCSzd3NkL-RlQn8X-eTA_-xH03xVd';
    
    let supabaseClient;
    let currentUser = null;
    let formData = { fullName: '', role: '', source: '', storeName: '', storeAddress: '', storeContact: '', category: '' };

    // --- ULTRA FAST PRIORITY CHECK (With Metadata Logic) ---
    (async function priorityInit() {
        try {
            supabaseClient = supabase.createClient(SB_URL, SB_KEY);

            // A. Check for OAuth Redirect Hash
            const hash = window.location.hash;
            if (hash && hash.includes('access_token')) {
                document.getElementById('status-text').innerText = "VERIFYING TOKEN...";
                const { data } = await supabaseClient.auth.getSession();
                if (data?.session) {
                    window.history.replaceState(null, null, window.location.pathname);
                    await checkUserProfile(data.session.user);
                    return;
                }
            }

            // B. Check Existing Session
            const { data: { session } } = await supabaseClient.auth.getSession();
            if (session) {
                await checkUserProfile(session.user);
            } else {
                window.location.href = '/'; 
            }
        } catch (e) {
            console.error("Init Error", e);
            alert("Connection Error. Please refresh.");
        }
    })();

    // --- CHECK USER LOGIC (UPDATED) ---
    async function checkUserProfile(user) {
        currentUser = user;
        document.getElementById('status-text').innerText = "CHECKING ACCOUNT STATUS...";

        // 1. FAST TRACK: Check Metadata First (No DB Call needed if flagged)
        if (user.user_metadata && user.user_metadata.onboarded === true) {
             console.log("Metadata found: Fast Redirect");
             document.getElementById('status-text').innerText = "WELCOME BACK!";
             window.location.href = '/dashboard';
             return;
        }

        // 2. FALLBACK: Check Database (If metadata is missing)
        const { data, error } = await supabaseClient
            .from('profiles')
            .select('role')
            .eq('id', user.id)
            .single();

        if (data && data.role) {
            // User Exists but Metadata was missing -> FIX IT
            console.log("User found in DB, updating metadata...");
            await supabaseClient.auth.updateUser({
                data: { onboarded: true, role: data.role }
            });
            window.location.href = '/dashboard';
        } else {
            // New User -> Show Wizard
            revealWizard();
        }
    }

    function revealWizard() {
        const loader = document.getElementById('auth-loader');
        const wizard = document.getElementById('wizard');
        
        loader.style.opacity = '0';
        setTimeout(() => { loader.style.display = 'none'; }, 400);

        wizard.style.display = 'block';
        if(typeof gsap !== 'undefined') {
            gsap.fromTo("#step1", {opacity: 0, x: 20}, {opacity: 1, x: 0, duration: 0.5});
        } else {
            document.getElementById('step1').classList.add('active');
        }
    }

    // --- FORM HANDLING ---
    window.validate = function(step) {
      let isValid = false;
      const btn = document.getElementById(`btn${step}`);
      if(!btn) return;

      if(step === 1) isValid = document.getElementById('fullName').value.length > 2;
      if(step === 3) isValid = document.getElementById('source').value !== "";
      if(step === 4) isValid = document.getElementById('storeName').value.length > 2;
      if(step === 5) isValid = document.getElementById('storeContact').value.length > 5;
      
      isValid ? btn.classList.add('enabled') : btn.classList.remove('enabled');
    }

    window.selectRole = function(role, el) {
      formData.role = role;
      document.querySelectorAll('.radio-card').forEach(c => c.classList.remove('selected'));
      el.classList.add('selected');
      document.getElementById('btn2').classList.add('enabled');
    }

    window.handleSourceNext = function() {
        formData.source = document.getElementById('source').value;
        if (formData.role === 'buyer') {
             submitData(); 
        } else {
             nextStep(4);
        }
    }

    window.nextStep = function(target) {
      const current = document.querySelector('.step-card.active');
      const next = document.getElementById(`step${target}`);
      if(!current || !next) return;

      const bar = document.querySelector('.active .progress-fill');
      if(bar) bar.style.width = `${(target/5)*100}%`;

      if(typeof gsap !== 'undefined') {
          gsap.to(current, { x: -30, opacity: 0, duration: 0.3, onComplete: () => {
             current.classList.remove('active'); current.style.visibility = 'hidden';
             next.style.visibility = 'visible'; next.classList.add('active');
             next.querySelector('.progress-fill').style.width = `${(target/5)*100}%`;
             gsap.fromTo(next, { x: 30, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3 });
          }});
      } else {
          current.classList.remove('active'); next.classList.add('active');
      }
    }

    window.prevStep = function(target) {
      const current = document.querySelector('.step-card.active');
      const prev = document.getElementById(`step${target}`);
      if(typeof gsap !== 'undefined') {
          gsap.to(current, { x: 30, opacity: 0, duration: 0.3, onComplete: () => {
             current.classList.remove('active'); current.style.visibility = 'hidden';
             prev.style.visibility = 'visible'; prev.classList.add('active');
             gsap.fromTo(prev, { x: -30, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3 });
          }});
      }
    }

    // --- SUBMIT DATA (UPDATED WITH METADATA FLAG) ---
    window.submitData = async function() {
        const btn = document.getElementById(formData.role === 'buyer' ? 'btn3' : 'btn5');
        btn.innerText = "Finishing...";
        
        formData.fullName = document.getElementById('fullName').value;
        if(formData.role === 'seller') {
            formData.storeName = document.getElementById('storeName').value;
            formData.storeAddress = document.getElementById('storeAddress').value;
            formData.storeContact = document.getElementById('storeContact').value;
            formData.category = document.getElementById('category').value;
        }

        try {
            // 1. Insert DB Profile
            const { error: pErr } = await supabaseClient.from('profiles').upsert({
                id: currentUser.id,
                full_name: formData.fullName,
                role: formData.role,
                referral_source: formData.source,
                updated_at: new Date()
            });
            if(pErr) throw pErr;

            // 2. Insert Store (If Seller)
            if(formData.role === 'seller') {
                const { error: sErr } = await supabaseClient.from('stores').insert([{
                    owner_id: currentUser.id,
                    store_name: formData.storeName,
                    address: formData.storeAddress,
                    contact_email: formData.storeContact,
                    category: formData.category
                }]);
                if(sErr) throw sErr;
            }

            // 3. SET METADATA FLAG (The "Stamp") 🚀
            await supabaseClient.auth.updateUser({
                data: { onboarded: true, role: formData.role }
            });

            window.location.href = '/dashboard';

        } catch (err) {
            console.error(err);
            alert("Error: " + err.message);
            btn.innerText = "Try Again";
        }
    }

    window.hardReset = async function() {
        await supabaseClient.auth.signOut();
        window.location.href = '/';
    }
  </script>
</body>
</html>
"""

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page():
    return ONBOARDING_HTML