import { Client, Stream } from 'k6/net/grpc';
import { check, sleep } from 'k6';

// List of all server ports defined in your docker-compose.yml
const PORTS = ['50051', '50052', '50053', '50054', '50055', '50056'];

const client = new Client();
client.load(['.'], 'fishing.proto');

export const options = {
  // Use a multiple of 6 to distribute users evenly
  vus: 100, 
  duration: '10s',
};

export default () => {
  // 1. Determine which server this VU should talk to
  // __VU starts at 1, so we use (modulo % length) to pick a port
  const portIndex = (__VU - 1) % PORTS.length;
  const targetPort = PORTS[portIndex];
  const serverAddr = `localhost:${targetPort}`;

  // Connect only on the first iteration for this VU
  if (__ITER == 0) {
    console.log(`VU ${__VU} connecting to server on port ${targetPort}`);
    client.connect(serverAddr, { plaintext: true });
  }

  const jwt = `user_${__VU}_on_${targetPort}`;

  // --- Unary: Login ---
  const loginRes = client.invoke('fishingapp.FishingService/Login', {
    username: `fisher${__VU}`,
    password: 'password'
  });
  check(loginRes, { 'login success': (r) => r });

  // --- Client-Streaming: UpdateLocation ---
  const updateStream = new Stream(client, 'fishingapp.FishingService/UpdateLocation');
  
  // Send 5 rapid location updates to this specific server
  for (let i = 0; i < 5; i++) {
    updateStream.write({
      jwt: jwt,
      x: Math.random() * 100,
      y: Math.random() * 100,
    });
  }
  updateStream.end();

//   // --- Server-Streaming: StartFishing ---
//   const fishingStream = new Stream(client, 'fishingapp.FishingService/StartFishing');
  
//   fishingStream.on('data', (fish) => {
//     console.log(`[Port ${targetPort}] VU ${__VU} caught: ${fish.fishDna}`);
//   });

//   fishingStream.write({ jwt: jwt });
//   fishingStream.end();

  // --- Unary: Inventory (Check state across all users on this server) ---
  const invRes = client.invoke('fishingapp.FishingService/Inventory', {});
  check(invRes, { 'inventory received': (r) => r.status });

  sleep(1);
};
