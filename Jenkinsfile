pipeline {
    agent any

    environment {
        IMAGE = "192.168.42.141:5000/aabhar-backend"
        TAG = "${env.BUILD_NUMBER}"
        DOCKER_BUILDKIT = "1"
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
        timestamps()
    }

    stages {
        stage('Checkout') {
            when {
                branch 'local-dev'
            }
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            when {
                branch 'local-dev'
            }
            steps {
                sh '''
                    docker build \
                        -t $IMAGE:$TAG \
                        -t $IMAGE:latest \
                        .
                '''
            }
        }

        stage('Push Docker Image') {
            when {
                branch 'local-dev'
            }
            steps {
                sh '''
                    docker push $IMAGE:$TAG
                    docker push $IMAGE:latest
                '''
            }
        }

        stage('Deploy to K3s') {
            when {
                branch 'local-dev'
            }
            steps {
                withCredentials([
                    file(
                        credentialsId: 'aabhar-k3s-kubeconfig',
                        variable: 'KUBECONFIG'
                    )
                ]) {
                    sh '''
                        set -eu

                        echo "Checking Kubernetes client..."
                        command -v kubectl
                        kubectl version --client

                        echo "Deploying image: $IMAGE:$TAG"

                        for service in \
                            auth \
                            roles \
                            employees \
                            wallet \
                            recognition \
                            rewards \
                            organization \
                            analytics
                        do
                            echo "Updating $service..."
                            kubectl set image \
                                deployment/$service \
                                $service=$IMAGE:$TAG \
                                -n aabhar
                        done

                        echo "Waiting for deployment rollouts..."

                        for service in \
                            auth \
                            roles \
                            employees \
                            wallet \
                            recognition \
                            rewards \
                            organization \
                            analytics
                        do
                            echo "Waiting for $service..."
                            kubectl rollout status \
                                deployment/$service \
                                -n aabhar \
                                --timeout=180s
                        done

                        echo "All eight services deployed successfully."
                    '''
                }
            }
        }
    }

    post {
        success {
            echo "Successfully built, pushed, and deployed ${IMAGE}:${TAG}"
        }

        failure {
            echo "Aabhar backend pipeline failed. Check the failed stage and deployment logs."
        }
    }
}
