function mostrar(id, valor) {
    const elemento = document.getElementById(id);
    if (elemento && valor) {
        elemento.textContent = valor;
    }
}

mostrar("libro-prestado-a", localStorage.getItem("prestadoA"));
mostrar("libro-fecha-devolucion", localStorage.getItem("fechaDevolucion"));
mostrar("libro-curso", localStorage.getItem("curso"));

if (localStorage.getItem("actualizado") === "si") {
    const mensaje = document.getElementById("mensajeActualizado");
    if (mensaje) {
        mensaje.classList.remove("d-none");
    }
    localStorage.removeItem("actualizado");
}