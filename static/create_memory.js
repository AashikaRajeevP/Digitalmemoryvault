(function () {
    "use strict";

    const form = document.getElementById("memory-form");
    if (!form || form.dataset.uploadsEnabled !== "true") {
        return;
    }

    const fileInput = document.getElementById("photo-input");
    const previewContainer = document.getElementById("photo-previews");
    const status = document.getElementById("upload-status");
    const hiddenPhotos = document.getElementById("photos-json");
    const submitButton = document.getElementById("memory-submit");

    const signatureUrl = form.dataset.signatureUrl;
    const maxPhotos = parseInt(form.dataset.maxPhotos, 10) || 10;
    const maxPhotoBytes = parseInt(form.dataset.maxPhotoBytes, 10) || 10485760;
    const maxPhotoMb = Math.max(1, Math.floor(maxPhotoBytes / (1024 * 1024)));

    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    const csrf = csrfToken ? csrfToken.content : "";

    const allowedTypes = new Set([
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    ]);
    const allowedExtension = /\.(jpe?g|png|webp|gif)$/i;

    const items = [];
    let nextId = 1;
    let uploadInProgress = false;

    function setStatus(message, isError) {
        status.textContent = message;
        status.dataset.state = isError ? "error" : "";
    }

    function setNote(item, message, isError) {
        item.note.textContent = message;
        item.note.classList.toggle("is-error", Boolean(isError));
    }

    function refreshHidden() {
        const completed = items.filter((item) => item.status === "done");
        const checked = form.querySelector('input[name="cover_choice"]:checked');
        const coverId = checked
            ? checked.value
            : completed.length
              ? String(completed[0].id)
              : null;

        const payload = completed.map((item, index) => ({
            public_id: item.publicId,
            secure_url: item.secureUrl,
            width: item.width,
            height: item.height,
            format: item.format,
            bytes: item.bytes,
            position: index,
            is_cover: String(item.id) === coverId,
        }));

        hiddenPhotos.value = payload.length ? JSON.stringify(payload) : "";
    }

    function refreshSubmitState() {
        submitButton.disabled = items.some(
            (item) => item.status === "uploading"
        );
    }

    function chooseCoverIfNeeded() {
        const checked = form.querySelector('input[name="cover_choice"]:checked');
        if (checked) {
            return;
        }
        const candidate =
            items.find((item) => item.status === "done") || items[0];
        if (candidate) {
            candidate.coverInput.checked = true;
        }
    }

    function removeItem(item) {
        if (item.xhr) {
            item.xhr.abort();
        }
        URL.revokeObjectURL(item.objectUrl);
        item.card.remove();
        const index = items.indexOf(item);
        if (index !== -1) {
            items.splice(index, 1);
        }
        chooseCoverIfNeeded();
        refreshHidden();
        refreshSubmitState();
    }

    function createPreview(file) {
        const item = {
            id: nextId++,
            file: file,
            status: "pending",
            publicId: null,
            secureUrl: null,
            width: null,
            height: null,
            format: null,
            bytes: file.size,
            objectUrl: URL.createObjectURL(file),
            xhr: null,
        };

        const card = document.createElement("div");
        card.className = "photo-preview";

        const image = document.createElement("img");
        image.src = item.objectUrl;
        image.alt = "Preview of " + file.name;

        const coverLabel = document.createElement("label");
        coverLabel.className = "photo-cover-choice";
        const coverInput = document.createElement("input");
        coverInput.type = "radio";
        coverInput.name = "cover_choice";
        coverInput.value = String(item.id);
        coverLabel.append(coverInput, document.createTextNode("Cover"));

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "photo-remove";
        removeButton.textContent = "Remove";
        removeButton.setAttribute("aria-label", "Remove " + file.name);
        removeButton.addEventListener("click", () => removeItem(item));

        const progress = document.createElement("progress");
        progress.max = 100;
        progress.value = 0;
        progress.hidden = true;

        const note = document.createElement("p");
        note.className = "photo-note";
        note.textContent = "Ready to upload";

        card.append(image, removeButton, coverLabel, progress, note);
        previewContainer.append(card);

        item.card = card;
        item.image = image;
        item.coverInput = coverInput;
        item.progress = progress;
        item.note = note;

        coverInput.addEventListener("change", refreshHidden);

        return item;
    }

    async function getSignature() {
        const response = await fetch(signatureUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": csrf,
                Accept: "application/json",
            },
        });

        let data = null;
        try {
            data = await response.json();
        } catch (error) {
            data = null;
        }

        if (
            !response.ok ||
            !data ||
            !data.upload_url ||
            !data.signature ||
            !data.api_key
        ) {
            throw new Error(
                "Photo uploads are not available right now. " +
                    "You can still create the memory without photos."
            );
        }

        return data;
    }

    function uploadToCloudinary(item, signature) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            item.xhr = xhr;
            xhr.open("POST", signature.upload_url, true);

            xhr.upload.addEventListener("progress", (event) => {
                if (!event.lengthComputable) {
                    return;
                }
                const percent = Math.round(
                    (event.loaded / event.total) * 100
                );
                item.progress.value = percent;
                setNote(item, "Uploading… " + percent + "%", false);
            });

            xhr.addEventListener("load", () => {
                let data = null;
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (error) {
                    data = null;
                }

                if (
                    xhr.status >= 200 &&
                    xhr.status < 300 &&
                    data &&
                    data.secure_url &&
                    data.public_id
                ) {
                    resolve(data);
                    return;
                }

                const errorMessage =
                    (data && data.error && data.error.message) ||
                    ("Upload failed. Use JPG, PNG, WebP, or GIF up to " +
                        maxPhotoMb +
                        " MB.");
                reject(new Error(errorMessage));
            });

            xhr.addEventListener("error", () => {
                reject(
                    new Error(
                        "Network error while uploading. Please try again."
                    )
                );
            });

            xhr.addEventListener("abort", () => {
                reject(new Error("Upload canceled."));
            });

            const formData = new FormData();
            formData.append("file", item.file);
            formData.append("api_key", signature.api_key);
            formData.append("timestamp", signature.timestamp);
            formData.append("folder", signature.folder);
            formData.append("allowed_formats", signature.allowed_formats);
            formData.append("signature", signature.signature);
            xhr.send(formData);
        });
    }

    async function uploadItem(item) {
        if (!items.includes(item)) {
            return;
        }

        item.status = "uploading";
        item.card.classList.add("is-uploading");
        setNote(item, "Requesting upload signature…", false);
        refreshSubmitState();
        refreshHidden();

        let signature;
        try {
            signature = await getSignature();
        } catch (error) {
            if (!items.includes(item)) {
                return;
            }
            item.status = "error";
            item.card.classList.remove("is-uploading");
            item.card.classList.add("photo-error");
            setNote(item, error.message, true);
            refreshSubmitState();
            return;
        }

        if (!items.includes(item)) {
            return;
        }

        setNote(item, "Uploading…", false);
        item.progress.hidden = false;

        try {
            const data = await uploadToCloudinary(item, signature);
            if (!items.includes(item)) {
                return;
            }

            item.status = "done";
            item.publicId = data.public_id;
            item.secureUrl = data.secure_url;
            item.width = data.width;
            item.height = data.height;
            item.format = data.format;
            item.bytes = data.bytes;

            item.image.src = data.secure_url;
            item.progress.value = 100;
            item.progress.hidden = true;
            item.card.classList.remove("is-uploading");
            setNote(item, "Uploaded", false);
            chooseCoverIfNeeded();
        } catch (error) {
            if (!items.includes(item)) {
                return;
            }
            item.status = "error";
            item.progress.hidden = true;
            item.card.classList.remove("is-uploading");
            item.card.classList.add("photo-error");
            setNote(item, error.message, true);
        } finally {
            if (items.includes(item)) {
                refreshSubmitState();
                refreshHidden();
            }
        }
    }

    function isAllowedFile(file) {
        if (allowedTypes.has(file.type)) {
            return true;
        }
        return !file.type && allowedExtension.test(file.name);
    }

    async function handleFiles(fileList) {
        if (uploadInProgress) {
            return;
        }

        const incoming = Array.from(fileList);
        if (!incoming.length) {
            return;
        }

        const remaining = maxPhotos - items.length;
        if (remaining <= 0) {
            setStatus(
                "You can attach up to " + maxPhotos + " photos.",
                true
            );
            return;
        }

        const accepted = [];
        for (const file of incoming) {
            if (accepted.length >= remaining) {
                setStatus(
                    "Only " + maxPhotos + " photos are allowed. " +
                        "Extra files were ignored.",
                    true
                );
                break;
            }
            if (!isAllowedFile(file)) {
                setStatus(
                    '"' + file.name + '" is not a supported image. ' +
                        "Use JPG, PNG, WebP, or GIF.",
                    true
                );
                continue;
            }
            if (file.size > maxPhotoBytes) {
                setStatus(
                    '"' + file.name + '" is too large. The maximum is ' +
                        maxPhotoMb + " MB.",
                    true
                );
                continue;
            }
            accepted.push(file);
        }

        if (!accepted.length) {
            return;
        }

        setStatus("", false);

        for (const file of accepted) {
            items.push(createPreview(file));
        }
        chooseCoverIfNeeded();
        refreshHidden();

        uploadInProgress = true;
        fileInput.disabled = true;
        refreshSubmitState();

        try {
            for (const item of items.filter(
                (entry) => entry.status === "pending"
            )) {
                await uploadItem(item);
            }
        } finally {
            uploadInProgress = false;
            fileInput.disabled = false;
            refreshSubmitState();
        }
    }

    fileInput.addEventListener("change", () => {
        handleFiles(fileInput.files);
        fileInput.value = "";
    });

    form.addEventListener("submit", (event) => {
        if (items.some((item) => item.status === "uploading")) {
            event.preventDefault();
            setStatus("Please wait for the photo uploads to finish.", true);
            return;
        }

        if (items.some((item) => item.status === "error")) {
            event.preventDefault();
            setStatus(
                "Some photos failed to upload. Remove them or try again " +
                    "before saving the memory.",
                true
            );
            return;
        }

        refreshHidden();
    });

    window.addEventListener("pagehide", () => {
        for (const item of items) {
            URL.revokeObjectURL(item.objectUrl);
        }
    });
})();
