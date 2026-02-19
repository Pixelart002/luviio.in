// Wait for DOM and GSAP to load
document.addEventListener('DOMContentLoaded', () => {
  if (typeof gsap === 'undefined') return;
  
  gsap.registerPlugin(ScrollTrigger);
  
  // Hero section animations with timeline
  const heroTimeline = gsap.timeline({
    scrollTrigger: {
      trigger: "section",
      start: "top 80%",
      end: "bottom 20%",
      scrub: 1,
    }
  });
  
  heroTimeline
    .from(".reveal-line", { y: 50, opacity: 0, duration: 1 })
    .from("h1", { y: 100, opacity: 0, duration: 1 }, "-=0.5")
    .from(".hero-p", { y: 30, opacity: 0, duration: 0.8 }, "-=0.3")
    .from(".hero-actions", { y: 30, opacity: 0, duration: 0.8 }, "-=0.2");
  
  // Parallax effect on hero orb
  gsap.to("#hero-orb", {
    y: 100,
    scrollTrigger: {
      trigger: "section",
      start: "top top",
      end: "bottom top",
      scrub: true,
    }
  });
  
  // Responsive: different animations on mobile?
  const mm = gsap.matchMedia();
  mm.add("(max-width: 768px)", () => {
    // Mobile-specific tweaks
    gsap.set("h1", { scale: 0.9 });
  });
});