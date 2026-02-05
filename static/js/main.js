// ===== NEURAL NETWORK CANVAS ANIMATION =====
class NeuralNetwork {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.particles = [];
        this.connections = [];
        this.mouse = { x: null, y: null };

        this.resize();
        this.init();

        window.addEventListener('resize', () => this.resize());
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    init() {
        const particleCount = Math.floor((this.canvas.width * this.canvas.height) / 15000);

        for (let i = 0; i < particleCount; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                radius: Math.random() * 2 + 1
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Update and draw particles
        this.particles.forEach((particle, i) => {
            // Update position
            particle.x += particle.vx;
            particle.y += particle.vy;

            // Bounce off edges
            if (particle.x < 0 || particle.x > this.canvas.width) particle.vx *= -1;
            if (particle.y < 0 || particle.y > this.canvas.height) particle.vy *= -1;

            // Mouse interaction
            if (this.mouse.x && this.mouse.y) {
                const dx = this.mouse.x - particle.x;
                const dy = this.mouse.y - particle.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < 150) {
                    const force = (150 - distance) / 150;
                    particle.x -= (dx / distance) * force * 2;
                    particle.y -= (dy / distance) * force * 2;
                }
            }

            // Draw particle
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(0, 240, 255, ${0.6})`;
            this.ctx.fill();

            // Draw connections
            this.particles.slice(i + 1).forEach(otherParticle => {
                const dx = particle.x - otherParticle.x;
                const dy = particle.y - otherParticle.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < 120) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(particle.x, particle.y);
                    this.ctx.lineTo(otherParticle.x, otherParticle.y);
                    const opacity = (120 - distance) / 120 * 0.3;
                    this.ctx.strokeStyle = `rgba(0, 128, 255, ${opacity})`;
                    this.ctx.lineWidth = 0.5;
                    this.ctx.stroke();
                }
            });
        });

        requestAnimationFrame(() => this.animate());
    }
}

// ===== SCROLL ANIMATIONS =====
class ScrollAnimations {
    constructor() {
        this.observerOptions = {
            threshold: 0.2,
            rootMargin: '0px 0px -100px 0px'
        };

        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, this.observerOptions);

        this.init();
    }

    init() {
        // Observe workflow steps
        document.querySelectorAll('.workflow-step').forEach((el, index) => {
            el.style.transitionDelay = `${index * 0.15}s`;
            this.observer.observe(el);
        });

        // Observe domain cards
        document.querySelectorAll('.domain-card').forEach((el, index) => {
            el.style.transitionDelay = `${index * 0.1}s`;
            this.observer.observe(el);
        });

        // Observe other fade-in elements
        document.querySelectorAll('.fade-in').forEach(el => {
            this.observer.observe(el);
        });
    }
}

// ===== 3D CARD TILT EFFECT =====
class CardTilt {
    constructor() {
        this.cards = document.querySelectorAll('.domain-card');
        this.init();
    }

    init() {
        this.cards.forEach(card => {
            card.addEventListener('mousemove', (e) => this.handleMouseMove(e, card));
            card.addEventListener('mouseleave', () => this.handleMouseLeave(card));
        });
    }

    handleMouseMove(e, card) {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        const rotateX = (y - centerY) / 10;
        const rotateY = (centerX - x) / 10;

        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(10px)`;
    }

    handleMouseLeave(card) {
        card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateZ(0)';
    }
}

// ===== PARALLAX EFFECT =====
class ParallaxEffect {
    constructor() {
        this.heroSection = document.querySelector('.hero-section');
        this.init();
    }

    init() {
        window.addEventListener('scroll', () => {
            const scrolled = window.pageYOffset;
            if (this.heroSection) {
                this.heroSection.style.transform = `translateY(${scrolled * 0.5}px)`;
                this.heroSection.style.opacity = 1 - (scrolled / 800);
            }
        });
    }
}

// ===== CTA BUTTON INTERACTION =====
class CTAButton {
    constructor() {
        this.button = document.querySelector('.cta-button');
        this.init();
    }

    init() {
        if (this.button) {
            this.button.addEventListener('click', (e) => {
                e.preventDefault();

                // Add click animation
                this.button.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    this.button.style.transform = '';
                }, 150);

                // Smooth page transition
                document.body.style.opacity = '0';
                document.body.style.transition = 'opacity 0.5s ease';

                setTimeout(() => {
                    window.location.href = '/select-role';
                }, 500);
            });
        }
    }
}

// ===== SMOOTH SCROLL =====
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// ===== INITIALIZE ALL =====
document.addEventListener('DOMContentLoaded', () => {
    // Initialize neural network animation
    const canvas = document.getElementById('neural-canvas');
    if (canvas) {
        const neuralNet = new NeuralNetwork(canvas);
        neuralNet.animate();
    }

    // Initialize scroll animations
    new ScrollAnimations();

    // Initialize 3D card tilt
    new CardTilt();

    // Initialize parallax effect
    new ParallaxEffect();

    // Initialize CTA button
    new CTAButton();

    // Initialize smooth scroll
    initSmoothScroll();

    // Add page load animation
    document.body.style.opacity = '0';
    setTimeout(() => {
        document.body.style.opacity = '1';
        document.body.style.transition = 'opacity 0.8s ease';
    }, 100);
});
