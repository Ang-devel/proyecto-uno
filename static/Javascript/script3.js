document.getElementById('btnGuardar').addEventListener('click', function () {
    const nombre = document.getElementById('nombre').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const mensajeError = document.getElementById('mensajeError');

    if (password !== confirmPassword) {
        mensajeError.classList.remove('d-none');
        return;
    }
    mensajeError.classList.add('d-none');

    // Guardamos los datos de la cuenta en localStorage
    const cuenta = { nombre, email, password };
    localStorage.setItem('cuenta', JSON.stringify(cuenta));

    // Vamos a inicio.html (podría ser Cuenta.html si prefieres ir directo ahí)
    window.location.href = 'inicio.html';
});