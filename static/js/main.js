const revealItems = document.querySelectorAll('.reveal, .word-rise');

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.16, rootMargin: '0px 0px -80px 0px' });

revealItems.forEach((item, index) => {
  item.style.transitionDelay = `${Math.min(index * 55, 360)}ms`;
  observer.observe(item);
});

const header = document.querySelector('[data-header]');

window.addEventListener('scroll', () => {
  if (!header) return;
  header.classList.toggle('is-scrolled', window.scrollY > 24);
}, { passive: true });
