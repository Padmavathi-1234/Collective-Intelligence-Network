const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });

const container = document.getElementById('canvas-container');
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

// Particles
const particlesGeometry = new THREE.BufferGeometry();
const particlesCount = 700; // Adjust for density
const posArray = new Float32Array(particlesCount * 3);

for(let i = 0; i < particlesCount * 3; i++) {
    // Spread particles in a wide area
    posArray[i] = (Math.random() - 0.5) * 15;
}

particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));

// Material for dots
const material = new THREE.PointsMaterial({
    size: 0.02,
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.8,
});

// Mesh
const particlesMesh = new THREE.Points(particlesGeometry, material);
scene.add(particlesMesh);

// Lines to connect particles (Neural Connection effect)
// Note: For high performance with many lines, we can use a simpler approach or LineSegments
// Here, we'll implement a custom shader or simple line loop if performance permits. 
// For better performance on web, let's use a group of lines that update dynamically or just stick to points and a subtle wireframe sphere.

// Let's add a wireframe sphere to represent the "Global Brain" center
const geometry = new THREE.IcosahedronGeometry(4, 2);
const wireframeMaterial = new THREE.MeshBasicMaterial({ 
    color: 0x4444ff, 
    wireframe: true, 
    transparent: true, 
    opacity: 0.05 
});
const sphere = new THREE.Mesh(geometry, wireframeMaterial);
scene.add(sphere);

// Mouse interaction
let mouseX = 0;
let mouseY = 0;

document.addEventListener('mousemove', (event) => {
    mouseX = event.clientX / window.innerWidth - 0.5;
    mouseY = event.clientY / window.innerHeight - 0.5;
});

// Lighting
const pointLight = new THREE.PointLight(0xffffff, 0.1);
pointLight.position.set(2, 3, 4);
scene.add(pointLight);

camera.position.z = 3;

// Animation Loop
const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    const elapsedTime = clock.getElapsedTime();

    // Rotate the entire particle system slowly
    particlesMesh.rotation.y = elapsedTime * 0.05;
    sphere.rotation.x = elapsedTime * 0.02;
    sphere.rotation.y = elapsedTime * 0.02;

    // Mouse Parallax effect
    particlesMesh.rotation.x += mouseY * 0.005;
    particlesMesh.rotation.y += mouseX * 0.005;

    // Gentle wave/pulse effect on particles could be added here iterating through positions
    // but kept simple for performance.

    renderer.render(scene, camera);
}

animate();

// Resizing
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});
