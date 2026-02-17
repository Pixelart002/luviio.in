/**
 * LUVIIO.IN - CORE ENGINE
 * Stack: GSAP ScrollTrigger + Unpoly
 */

gsap.registerPlugin(ScrollTrigger);

// 1. Initial Load Config
window.addEventListener("load", () => {
    document.body.style.opacity = "1";
    document.body.style.visibility = "visible";
    initAnimations();
});

// 2. Unpoly Hooks (SPA Behavior)
// When a new fragment is inserted, re-initialize animations
up.on('up:fragment:inserted', (event) => {
    // Kill old ScrollTriggers to prevent memory leaks/conflicts
    ScrollTrigger.getAll().forEach(t => t.kill());
    // Reset window scroll to top if needed
    window.scrollTo(0, 0);
    // Re-run animation logic
    initAnimations();
});

// 3. Animation Factory
function initAnimations() {
    console.log("Luviio: Animations Initialized");

    // --- HERO SEQUENCE ---
    if (document.querySelector('#hero')) {
        const tl = gsap.timeline();
        
        tl.from(".hero-title", {
            y: 100,
            opacity: 0,
            duration: 1.5,
            ease: "power4.out",
            skewY: 7
        })
        .to(".hero-subtitle", {
            y: 0,
            opacity: 1,
            duration: 1,
            ease: "power2.out"
        }, "-=1");

        // Parallax Hero Background
        gsap.to("#hero", {
            scrollTrigger: {
                trigger: "#hero",
                start: "top top",
                end: "bottom top",
                scrub: true
            },
            y: "30%",
            ease: "none"
        });
    }

    // --- HORIZONTAL SCROLL SHOWCASE ---
    const showcaseTrack = document.getElementById("showcase-track");
    const showcaseSection = document.getElementById("showcase-pin");

    if (showcaseTrack && showcaseSection) {
        // Calculate the width to scroll
        // (Track width - Viewport width)
        let getScrollAmount = () => -(showcaseTrack.scrollWidth - window.innerWidth);

        const tween = gsap.to(showcaseTrack, {
            x: getScrollAmount,
            ease: "none",
        });

        ScrollTrigger.create({
            trigger: showcaseSection,
            start: "top top",
            end: () => `+=${showcaseTrack.scrollWidth - window.innerWidth}`,
            pin: true,
            animation: tween,
            scrub: 1,
            invalidateOnRefresh: true, // Recalculate on resize
            // markers: true // Uncomment for debugging
        });
    }

    // --- TECH STACK GRID REVEAL ---
    const techItems = document.querySelectorAll(".tech-item");
    if (techItems.length > 0) {
        gsap.from(techItems, {
            scrollTrigger: {
                trigger: "#tech-grid",
                start: "top 80%",
            },
            y: 50,
            opacity: 0,
            duration: 0.8,
            stagger: 0.1,
            ease: "power3.out"
        });
    }

    // --- CTA CIRCLE EXPLOSION ---
    const ctaCircle = document.querySelector(".cta-circle");
    if (ctaCircle) {
        gsap.to(ctaCircle, {
            scrollTrigger: {
                trigger: "#cta-section",
                start: "top center",
                end: "bottom bottom",
                scrub: 1
            },
            scale: 1,
            ease: "expo.out"
        });
    }
}