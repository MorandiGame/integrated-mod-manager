/** Missing previews get one fallback attempt; a missing fallback must not loop. */
export function applyImageFallback(image: HTMLImageElement, fallback: string, hide = false): void {
	if (hide || image.getAttribute("src") === fallback) {
		image.style.opacity = "0";
		image.classList.remove("fadein");
	}
	if (image.getAttribute("src") === fallback) return;
	image.src = fallback;
}
