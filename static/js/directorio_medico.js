(() => {
  const root = document.querySelector('[data-directory-root]');
  if (!root) return;
  const cards = Array.from(root.querySelectorAll('[data-directory-card]'));
  const inputs = {
    name: root.querySelector('[data-directory-filter="name"]'),
    specialty: root.querySelector('[data-directory-filter="specialty"]'),
    city: root.querySelector('[data-directory-filter="city"]')
  };
  const count = root.querySelector('[data-directory-count]');
  const empty = root.querySelector('[data-directory-empty]');
  const more = root.querySelector('[data-directory-more]');
  const clear = root.querySelector('[data-directory-clear]');
  const pageSize = Number(root.dataset.mobilePageSize || 5);
  let mobileVisible = pageSize;
  const normalize = value => (value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const isMobile = () => window.matchMedia('(max-width: 620px)').matches;
  const values = () => ({name:normalize(inputs.name?.value),specialty:normalize(inputs.specialty?.value),city:normalize(inputs.city?.value)});
  const hasFilter = filters => Boolean(filters.name || filters.specialty || (filters.city && filters.city !== 'tijuana'));

  function render() {
    const filters = values();
    const matches = cards.filter(card => (!filters.name || normalize(card.dataset.name).includes(filters.name))
      && (!filters.specialty || normalize(card.dataset.specialty).includes(filters.specialty))
      && (!filters.city || normalize(card.dataset.city).includes(filters.city)));
    const filtered = hasFilter(filters);
    cards.forEach(card => {
      const index = matches.indexOf(card);
      card.hidden = index < 0 || (isMobile() && !filtered && index >= mobileVisible);
    });
    if (count) count.textContent = `${matches.length} perfil${matches.length === 1 ? '' : 'es'}`;
    if (empty) empty.hidden = matches.length !== 0;
    if (more) {
      const remaining = isMobile() && !filtered ? matches.length - mobileVisible : 0;
      more.hidden = remaining <= 0;
      more.textContent = remaining > 0 ? `Ver más médicos (${remaining})` : 'Ver más médicos';
    }
  }
  Object.values(inputs).forEach(input => input?.addEventListener('input', () => { mobileVisible = pageSize; render(); }));
  more?.addEventListener('click', () => { mobileVisible += pageSize; render(); });
  clear?.addEventListener('click', () => {
    if (inputs.name) inputs.name.value = '';
    if (inputs.specialty) inputs.specialty.value = '';
    mobileVisible = pageSize;
    render();
    inputs.name?.focus();
  });
  window.addEventListener('resize', render);
  render();
})();
