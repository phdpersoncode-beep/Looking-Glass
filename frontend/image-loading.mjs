// Listen before assigning src so cached loads cannot race handler registration.
export function loadImage(image, source){
  return new Promise((resolve,reject)=>{
    const clear=()=>{image.removeEventListener('load',loaded);image.removeEventListener('error',failed);};
    const loaded=()=>{clear();resolve(image);};
    const failed=()=>{clear();reject(new Error('Unable to load image.'));};
    image.addEventListener('load',loaded);image.addEventListener('error',failed);
    image.src=source;
  });
}
