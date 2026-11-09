const formulario = document.getElementById("formPrestamo");

formulario.addEventListener("submit", function(event) {
    event.preventDefault();

    localStorage.setItem("prestadoA", document.getElementById("usuario").value);
    localStorage.setItem("curso", document.getElementById("curso").value);
    localStorage.setItem("fechaDevolucion", document.getElementById("fechadevolucion").value);

    localStorage.setItem("actualizado", "si");

    window.location.href = "Info.Libro.html";
});