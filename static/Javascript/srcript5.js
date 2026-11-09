// ===== Código que ya tenías =====
const cuentaGuardada = localStorage.getItem('cuenta');
if (cuentaGuardada) {
    const link = document.getElementById('linkCuenta');
    if (link) {
        link.textContent = 'Cuenta';
        link.setAttribute('href', '/cuenta');
    }
}

// ===== Buscador de libros =====
document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector('form[role="search"]');
    if (!form) return;
    var input = form.querySelector('input[type="search"]');
    if (!input) return;

    // Quita tildes y pasa a minúsculas: "Niño" == "nino", "Odisea" == "odisea"
    function normalizar(texto) {
        return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    }

    // Todas las tarjetas de libros de la página (con su columna)
    var items = [];
    document.querySelectorAll(".card").forEach(function (card) {
        var columna = card.closest(".col") || card;
        // Se busca solo por título (h4/h5) y autor (el <p> justo debajo)
        var partes = card.querySelectorAll("h4, h5, h4 + p, h5 + p");
        var texto = "";
        partes.forEach(function (el) { texto += " " + el.textContent; });
        items.push({ columna: columna, texto: normalizar(texto) });
    });

    // Mensaje cuando no hay resultados
    var mensaje = document.createElement("p");
    mensaje.className = "text-center fw-bold mt-4";
    mensaje.style.display = "none";
    mensaje.textContent = "No se encontraron libros con esa búsqueda.";
    if (items.length > 0) {
        var fila = items[0].columna.parentElement;
        fila.insertAdjacentElement("afterend", mensaje);
    }

    function filtrar() {
        var consulta = normalizar(input.value);
        var visibles = 0;
        items.forEach(function (item) {
            var coincide = consulta === "" || item.texto.indexOf(consulta) !== -1;
            item.columna.style.display = coincide ? "" : "none";
            if (coincide) visibles++;
        });
        mensaje.style.display = (visibles === 0 && items.length > 0) ? "" : "none";
    }

    input.addEventListener("input", filtrar);
    form.addEventListener("submit", function (e) {
        e.preventDefault(); // evita que la página se recargue
        filtrar();
    });
});