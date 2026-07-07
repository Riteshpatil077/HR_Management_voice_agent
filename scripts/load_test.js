import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate } from 'k6/metrics';

// Custom metrics
const ErrorRate = new Rate('errors');
const SuccessfulCalls = new Counter('successful_calls');

// K6 Configuration
export const options = {
  stages: [
    { duration: '1m', target: 50 },  // Ramp-up to 50 users over 1 minute
    { duration: '3m', target: 50 },  // Stay at 50 users for 3 minutes
    { duration: '1m', target: 100 }, // Spike to 100 users
    { duration: '3m', target: 100 }, // Hold spike
    { duration: '1m', target: 0 },   // Ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // 95% of requests < 500ms
    errors: ['rate<0.01'],                          // Error rate < 1%
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const JWT_TOKEN = __ENV.JWT_TOKEN || 'test-token';

const params = {
  headers: {
    'Authorization': `Bearer ${JWT_TOKEN}`,
    'Content-Type': 'application/json',
  },
};

export default function () {
  // 1. Create an interview
  const interviewPayload = JSON.stringify({
    candidate_name: `Load Test Candidate ${__VU}`,
    candidate_email: `load.test.${__VU}@example.com`,
    role: "Senior Engineer"
  });

  const interviewRes = http.post(`${BASE_URL}/v1/interviews/schedule`, interviewPayload, params);
  
  const interviewSuccess = check(interviewRes, {
    'interview created (200)': (r) => r.status === 200,
  });
  
  if (!interviewSuccess) {
    ErrorRate.add(1);
  } else {
    SuccessfulCalls.add(1);
    
    // 2. Fetch the created interview
    const data = JSON.parse(interviewRes.body);
    const fetchRes = http.get(`${BASE_URL}/v1/interviews/${data.interview_id}`, params);
    
    check(fetchRes, {
      'interview fetched (200)': (r) => r.status === 200,
    });
  }

  // 3. Simulate user wait time
  sleep(Math.random() * 2 + 1); // Random sleep between 1-3 seconds
}
