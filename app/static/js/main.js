// (theme switching removed)

// Apply theme immediately to avoid flash of wrong theme on first paint.
try{
  const THEME_KEY = 'site-theme';
  const root = document.documentElement;
  const stored = localStorage.getItem(THEME_KEY);
  if(stored){
    root.setAttribute('data-theme', stored);
  } else {
    root.setAttribute('data-theme', 'light');
  }
}catch(e){/* ignore localStorage errors */}

document.addEventListener('DOMContentLoaded', function(){
  const email = document.querySelector('input[name="username"]');
  const modeToggle = document.getElementById('mode-toggle');
  const modeLogin = null;
  const modeRegister = null;
  const confirmRow = document.getElementById('confirm-row');
  const confirmInput = document.getElementById('confirm');
  const form = document.getElementById('auth-form');
  const submitBtn = document.getElementById('submit-btn');
  const errorBox = document.getElementById('auth-error');
  const themeToggle = document.getElementById('theme-toggle');
  console.log(window.__AUTH_ERROR__);

  if(email){ email.focus(); }

  let mode = 'login';

  function setMode(m){
    mode = m;
    if(mode === 'login'){
      // visually set switch to off (login)
      if(modeToggle){ modeToggle.classList.remove('on'); modeToggle.setAttribute('aria-pressed','false'); }
      confirmRow.classList.add('hidden');
      submitBtn.textContent = 'Log In';
      form.action = '/login';
      //errorBox.textContent = '';
      confirmInput.removeAttribute('required');
    } else {
      // visually set switch to on (register)
      if(modeToggle){ modeToggle.classList.add('on'); modeToggle.setAttribute('aria-pressed','true'); }
      confirmRow.classList.remove('hidden');
      submitBtn.textContent = 'Register';
      form.action = '/register';
      //errorBox.textContent = window.__AUTH_ERROR__;
      confirmInput.setAttribute('required','');
    }
  }

  // toggle control
  if(modeToggle){
    modeToggle.addEventListener('click', function(){
      setMode(mode === 'login' ? 'register' : 'login');
    });
    modeToggle.addEventListener('keydown', function(e){
      if(e.key === ' ' || e.key === 'Enter'){
        e.preventDefault();
        setMode(mode === 'login' ? 'register' : 'login');
      }
    });
  }
  // theme toggle button
  if(themeToggle){
    const knob = themeToggle.querySelector('.theme-knob');
    function updateThemeSwitch(t){
      if(t === 'dark'){
        themeToggle.classList.add('on');
        themeToggle.setAttribute('aria-pressed','true');
      } else {
        themeToggle.classList.remove('on');
        themeToggle.setAttribute('aria-pressed','false');
      }
    }
    // initialize switch
    try{ updateThemeSwitch(document.documentElement.getAttribute('data-theme') || 'light'); }catch(e){}
    themeToggle.addEventListener('click', function(){
      const cur = document.documentElement.getAttribute('data-theme') || 'light';
      const next = cur === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', next);
      try{ localStorage.setItem('site-theme', next); }catch(e){}
      updateThemeSwitch(next);
    });
  }
  // initialize UI to current mode
  setMode(mode);
  // theme switching removed — no-op here

  // validate on submit
  form && form.addEventListener('submit', function(e){
    if(mode === 'register'){
      if(!confirmInput.value || confirmInput.value !== document.getElementById('password').value){
        e.preventDefault();
        errorBox.textContent = 'Passwords do not match.';
        confirmInput.focus();
        return false;
      }
    }
    return true;
  });
});
