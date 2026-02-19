up.on('up:layer:opened', (event) => {
  if (event.layer.mode === 'drawer') {
    const btn = document.querySelector('.hamburger-btn');
    if (!btn) return;
    const spans = btn.querySelectorAll('span');
    if (spans.length === 3) {
      gsap.to(spans[0], { rotate: 45, y: 9, duration: 0.3 });
      gsap.to(spans[1], { opacity: 0, x: -10, duration: 0.3 });
      gsap.to(spans[2], { rotate: -45, y: -9, duration: 0.3 });
    }
  }
});

up.on('up:layer:dismissed', (event) => {
  const btn = document.querySelector('.hamburger-btn');
  if (!btn) return;
  const spans = btn.querySelectorAll('span');
  if (spans.length === 3) {
    gsap.to(spans[0], { rotate: 0, y: 0, duration: 0.3 });
    gsap.to(spans[1], { opacity: 1, x: 0, duration: 0.3 });
    gsap.to(spans[2], { rotate: 0, y: 0, duration: 0.3 });
  }
});