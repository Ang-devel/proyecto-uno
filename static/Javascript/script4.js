const cuentaGuardada = JSON.parse(localStorage.getItem('cuenta'));
if (cuentaGuardada) {
    document.getElementById('nombreCuenta').textContent = cuentaGuardada.nombre;
    document.getElementById('emailCuenta').textContent = cuentaGuardada.email;
    document.getElementById('passwordCuenta').textContent = cuentaGuardada.password;
}