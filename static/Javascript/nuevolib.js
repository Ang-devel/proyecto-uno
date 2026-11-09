// Script de NuevoLibro.html: vista previa de la portada, validaciones y envío del formulario.

const TAMANO_MAXIMO_MB = 5;
const TIPOS_PERMITIDOS = ["image/png", "image/jpeg", "image/gif", "image/webp"];

// Imagen gris de "Sin imagen" (no depende de ningún sitio externo)
const SIN_IMAGEN =
    "data:image/svg+xml;charset=UTF-8," +
    encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="90" height="120">' +
        '<rect width="100%" height="100%" fill="#e9ecef"/>' +
        '<text x="50%" y="50%" font-family="Arial" font-size="12" fill="#6c757d" ' +
        'text-anchor="middle" dominant-baseline="middle">Sin imagen</text></svg>'
    );

function mostrarMensajePortada(input, texto) {
    let aviso = document.getElementById("avisoPortada");
    if (!aviso) {
        aviso = document.createElement("div");
        aviso.id = "avisoPortada";
        aviso.className = "text-danger small mt-1";
        input.insertAdjacentElement("afterend", aviso);
    }
    aviso.textContent = texto;
}

function mostrarPreview(input) {
    const preview = document.getElementById('previewPortada');
    mostrarMensajePortada(input, "");

    // Si se quitó el archivo, vuelve a la imagen "Sin imagen"
    if (!input.files || !input.files[0]) {
        preview.src = SIN_IMAGEN;
        return;
    }

    const archivo = input.files[0];

    if (!TIPOS_PERMITIDOS.includes(archivo.type)) {
        mostrarMensajePortada(input, "Elige una imagen PNG, JPG, GIF o WEBP.");
        input.value = "";
        preview.src = SIN_IMAGEN;
        return;
    }

    if (archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024) {
        mostrarMensajePortada(input, "La imagen pesa más de " + TAMANO_MAXIMO_MB + " MB.");
        input.value = "";
        preview.src = SIN_IMAGEN;
        return;
    }

    const reader = new FileReader();
    reader.onload = function (e) {
        preview.src = e.target.result;
    };
    reader.readAsDataURL(archivo);
}

document.addEventListener("DOMContentLoaded", function () {
    const preview = document.getElementById('previewPortada');
    if (preview) preview.src = SIN_IMAGEN;

    const formulario = document.querySelector('form[enctype="multipart/form-data"]');
    if (!formulario) return;

    formulario.addEventListener("submit", function (evento) {
        // El título no puede estar vacío ni ser solo espacios
        const titulo = formulario.querySelector('[name="titulo"]');
        if (titulo && titulo.value.trim() === "") {
            evento.preventDefault();
            titulo.classList.add("is-invalid");
            titulo.focus();
            return;
        }

        // Evita guardar el mismo libro dos veces si se hace doble clic
        const boton = formulario.querySelector('button[type="submit"]');
        if (boton) {
            boton.disabled = true;
            boton.textContent = "Guardando...";
        }
    });

    const titulo = formulario.querySelector('[name="titulo"]');
    if (titulo) {
        titulo.addEventListener("input", function () {
            titulo.classList.remove("is-invalid");
        });
    }
});